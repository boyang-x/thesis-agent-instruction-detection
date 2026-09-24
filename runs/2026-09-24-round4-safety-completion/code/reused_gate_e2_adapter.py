"""Tool-executor enforcement boundary for ProofClarify Gate E2.

This module contains no provider client.  A witness policy is injected as a
callable, which lets the same executor run deterministic oracle tests and later
use a frozen span extractor without changing the execution boundary.
"""

from __future__ import annotations

import copy
from ast import literal_eval
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from agentdojo.agent_pipeline.llms.google_llm import EMPTY_FUNCTION_NAME
from agentdojo.agent_pipeline.tool_execution import ToolsExecutor, is_string_list
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionCall, FunctionsRuntime
from agentdojo.types import (
    ChatMessage,
    ChatToolResultMessage,
    text_content_block_from_string,
)

from proofclarify_research.trace_attestation import value_sha256

ADAPTER_VERSION = "proofclarify-gate-e2-agentdojo-adapter-v0.2"
_EMPTY_ENV = EmptyEnv()
DecisionPolicy = Callable[
    [str, FunctionsRuntime, Env, Sequence[ChatMessage], FunctionCall],
    Mapping[str, Any],
]


def _normalize_decision(value: Mapping[str, Any]) -> dict[str, Any]:
    decision = value.get("decision")
    if decision not in {"ALLOW", "BLOCK", "ASK"}:
        raise ValueError("policy decision must be ALLOW, BLOCK, or ASK")
    reason = value.get("reason")
    if not isinstance(reason, str) or not reason:
        raise ValueError("policy decision must include a non-empty reason")
    return {**dict(value), "decision": decision, "reason": reason}


def _blocked_result(call: FunctionCall, decision: Mapping[str, Any]) -> ChatToolResultMessage:
    label = decision["decision"]
    reason = decision["reason"]
    return ChatToolResultMessage(
        role="tool",
        content=[
            text_content_block_from_string(
                f"ProofClarify {label}: tool call was not executed ({reason})."
            )
        ],
        tool_call_id=call.id,
        tool_call=call,
        error=f"ProofClarify{label}: {reason}",
    )


class GuardedToolsExecutor(ToolsExecutor):
    """Run the frozen policy immediately before each proposed tool call."""

    def __init__(
        self,
        policy: DecisionPolicy,
        *,
        tool_output_formatter=None,
    ) -> None:
        if tool_output_formatter is None:
            super().__init__()
        else:
            super().__init__(tool_output_formatter=tool_output_formatter)
        self.policy = policy

    def _execute_allowed_call(
        self,
        runtime: FunctionsRuntime,
        env: Env,
        call: FunctionCall,
    ) -> tuple[ChatToolResultMessage, Any, bool]:
        """Mirror AgentDojo execution while retaining the pre-format raw result."""
        if call.function == EMPTY_FUNCTION_NAME:
            return (
                ChatToolResultMessage(
                    role="tool",
                    content=[text_content_block_from_string("")],
                    tool_call_id=call.id,
                    tool_call=call,
                    error=(
                        "Empty function name provided. Provide a valid function name."
                    ),
                ),
                None,
                False,
            )
        if call.function not in (tool.name for tool in runtime.functions.values()):
            return (
                ChatToolResultMessage(
                    role="tool",
                    content=[text_content_block_from_string("")],
                    tool_call_id=call.id,
                    tool_call=call,
                    error=f"Invalid tool {call.function} provided.",
                ),
                None,
                False,
            )
        for key, value in call.args.items():
            if isinstance(value, str) and is_string_list(value):
                call.args[key] = literal_eval(value)
        raw_result, error = runtime.run_function(
            env,
            call.function,
            call.args,
        )
        formatted = self.output_formatter(raw_result)
        return (
            ChatToolResultMessage(
                role="tool",
                content=[text_content_block_from_string(formatted)],
                tool_call_id=call.id,
                tool_call=call,
                error=error,
            ),
            raw_result,
            True,
        )

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = _EMPTY_ENV,
        messages: Sequence[ChatMessage] = (),
        extra_args: dict | None = None,
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ChatMessage], dict]:
        extras = {} if extra_args is None else extra_args
        if (
            not messages
            or messages[-1]["role"] != "assistant"
            or not messages[-1].get("tool_calls")
        ):
            return query, runtime, env, messages, extras

        assistant = messages[-1]
        calls = list(assistant.get("tool_calls") or [])
        results: list[ChatToolResultMessage] = []
        audit_rows = list(getattr(runtime, "_proofclarify_audit", []))
        for call_index, call in enumerate(calls):
            try:
                decision = _normalize_decision(
                    self.policy(query, runtime, env, messages, call)
                )
            except Exception as error:
                decision = {
                    "decision": "BLOCK",
                    "reason": "policy_error_fail_closed",
                    "policy_error_type": type(error).__name__,
                    "policy_error": str(error),
                }
            audit = {
                "adapter_version": ADAPTER_VERSION,
                "call_index": call_index,
                "call_id": call.id,
                "tool": call.function,
                "arguments_sha256": value_sha256(dict(call.args)),
                **decision,
                "executed": False,
                "tool_error": None,
                "result_sha256": None,
            }
            if decision["decision"] != "ALLOW":
                results.append(_blocked_result(call, decision))
                audit_rows.append(audit)
                continue

            tool_result, raw_result, raw_result_available = (
                self._execute_allowed_call(runtime, env, call)
            )
            results.append(tool_result)
            content = "\n".join(
                block.get("content", "") for block in tool_result["content"]
            )
            audit.update(
                {
                    "executed": tool_result.get("error") is None,
                    "tool_error": tool_result.get("error"),
                    "result_sha256": value_sha256(content),
                }
            )
            observer = getattr(self.policy, "observe_tool_result", None)
            if callable(observer):
                observer(
                    runtime,
                    env,
                    call,
                    content,
                    tool_result.get("error"),
                    raw_result=raw_result,
                    raw_result_available=raw_result_available,
                )
            audit_rows.append(audit)

        runtime._proofclarify_audit = audit_rows
        return query, runtime, env, [*messages, *results], extras


def instrument_pipeline_with_proofclarify(
    pipeline: Any,
    policy: DecisionPolicy,
) -> int:
    """Replace every native ToolsExecutor in an AgentDojo/ASPI pipeline.

    The mutation is intentional: LLM client objects embedded in pipelines are
    not guaranteed to support ``deepcopy``.  The return value is the number of
    execution boundaries replaced and must be asserted by the caller.
    """

    replaced = 0
    elements = getattr(pipeline, "elements", None)
    if elements is None:
        return 0
    mutable = list(elements)
    for index, element in enumerate(mutable):
        if isinstance(element, GuardedToolsExecutor):
            continue
        if isinstance(element, ToolsExecutor):
            mutable[index] = GuardedToolsExecutor(
                policy,
                tool_output_formatter=element.output_formatter,
            )
            replaced += 1
            continue
        replaced += instrument_pipeline_with_proofclarify(element, policy)
    pipeline.elements = mutable
    pipeline._proofclarify_instrumentation = {
        "adapter_version": ADAPTER_VERSION,
        "executor_boundaries_replaced": replaced,
    }
    return replaced


class MappingDecisionPolicy:
    """Small deterministic policy used for boundary and scorer preflights."""

    def __init__(
        self,
        decisions: Mapping[str, str],
        *,
        default: str = "BLOCK",
    ) -> None:
        self.decisions = dict(decisions)
        self.default = default

    def __call__(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env,
        messages: Sequence[ChatMessage],
        call: FunctionCall,
    ) -> Mapping[str, Any]:
        del query, runtime, env, messages
        decision = self.decisions.get(call.function, self.default)
        return {
            "decision": decision,
            "reason": f"mapping_policy_{decision.lower()}",
        }


def clone_messages(messages: Sequence[ChatMessage]) -> list[ChatMessage]:
    """Public helper for branch-safe synthetic tests."""
    return copy.deepcopy(list(messages))
