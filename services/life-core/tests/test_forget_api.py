from app.assistant_plan import AssistantPlan, AssistantTask
from app.memory_forget import ForgetSelection
from test_api import make_app, bootstrap


def test_planning_does_not_mutate_and_forget_executes_only_owned_selection(tmp_path, monkeypatch):
    app, client = make_app(tmp_path)
    with client:
        bootstrap(client)
        monkeypatch.setattr(app.state.planner, 'plan', lambda *_a, **_kw:
                            AssistantPlan(tasks=[AssistantTask(action='forget_memory')]))
        payload = {'source_user_id':'lc-user-a','source_message_id':'f1','conversation_id':'c','query':'忘记住址'}
        headers = {'X-Internal-Token':'test-internal'}
        assert client.post('/internal/v1/assistant/plan',json=payload,headers=headers).json()['status']=='planned'
        assert client.post('/internal/v1/assistant/execute',json=payload,headers=headers).json()['results']==[
            {'action':'forget_memory','status':'needs_execution'}]
        body = {k:v for k,v in payload.items() if k!='query'} | {'text':payload['query']}
        assert client.post('/internal/v1/memory/forget',json=body).status_code==401
        monkeypatch.setattr(app.state.forget_memory,'select',lambda *_: ForgetSelection(intent='forget'))
        assert client.post('/internal/v1/memory/forget',json=body,headers=headers).json()=={'status':'no_match'}
        assert client.post('/internal/v1/memory/forget',json={**body,'source_user_id':'other'},headers=headers).json()=={
            'status':'user_not_mapped'}
