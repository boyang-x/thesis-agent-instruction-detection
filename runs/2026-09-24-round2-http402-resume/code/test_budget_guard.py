"""Mock-only safety checks; these tests never call any model service."""
import json
from unittest.mock import patch,MagicMock
import resume
from common import dump,writel,readl

real=resume.HERE;before=len(readl(real/'api_attempts.jsonl'))
request={'model':resume.F['model'],'temperature':0,'max_tokens':800,'messages':[{'role':'user','content':'mock'}]}
fixture=real/'guard_test_fixtures';fixture.mkdir(exist_ok=True)
case=fixture/'stop402';case.mkdir(exist_ok=False)
resp=MagicMock();resp.status_code=402;resp.text='mock insufficient balance'
client=MagicMock();client.__enter__.return_value.post.return_value=resp
with patch.object(resume,'HERE',case),patch.object(resume,'read_environment_value',return_value='mock-not-a-credential'),patch.object(resume.httpx,'Client',return_value=client):
    r=resume.send(request,'mock_402','test');assert r['error_code']=='HTTP_402'
    try:resume.send(request,'must_not_send','test');raise AssertionError('did not stop')
    except RuntimeError as exc:assert 'stopped' in str(exc)
    assert client.__enter__.return_value.post.call_count==1
case=fixture/'count200';case.mkdir(exist_ok=False)
writel(case/'api_calls.jsonl',[{'cost_reserved_or_estimated_CNY':0}]*200);writel(case/'api_attempts.jsonl',[{}]*200)
with patch.object(resume,'HERE',case),patch.object(resume.httpx,'Client') as client:
    try:resume.send(request,'must_not_send','test');raise AssertionError('did not cap')
    except RuntimeError as exc:assert 'budget' in str(exc)
    assert not client.called
case=fixture/'money10';case.mkdir(exist_ok=False)
writel(case/'api_calls.jsonl',[{'cost_reserved_or_estimated_CNY':10}]);writel(case/'api_attempts.jsonl',[{}])
with patch.object(resume,'HERE',case),patch.object(resume.httpx,'Client') as client:
    try:resume.send(request,'must_not_send','test');raise AssertionError('did not cap')
    except RuntimeError as exc:assert 'budget' in str(exc)
    assert not client.called
assert len(readl(real/'api_attempts.jsonl'))==before==190
dump(real/'guard_validation.json',{'status':'PASS','HTTP402_blocks_next_request':True,'request_cap_200':True,'estimated_cost_cap_10_CNY':True,'all_network_mocked':True,'real_requests_unchanged':190})
print('GUARD_TESTS_PASS_NO_API_CALLS')
