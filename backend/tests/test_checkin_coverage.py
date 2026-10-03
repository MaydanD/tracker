from datetime import date, timedelta

from tests.helpers import habit_payload


def test_calendar_counts_answers_independently_of_scores(client, health_area):
    today = client.get('/api/dashboard').json()['today']

    def counts(day=today):
        response = client.get('/api/calendar', params={'start': day, 'end': day})
        assert response.status_code == 200, response.text
        summary = response.json()[0]
        return summary['total_items'], summary['answered_items']

    assert counts() == (0, 0)
    completion = client.post('/api/habits', json=habit_payload(area_id=health_area['id'])).json()['id']
    scale = client.post('/api/habits', json=habit_payload(
        area_id=health_area['id'], name='Scale', value_type='binary',
        value_labels=['No', 'Yes'], direction='neutral',
    )).json()['id']
    assert counts() == (2, 0)
    assert counts(str(date.fromisoformat(today) - timedelta(days=1))) == (0, 0)
    endpoint = f'/api/habits/{completion}/entries/{today}'
    for status in ['done', 'missed', 'skipped']:
        payload = {'status': status}
        if status == 'skipped':
            payload['skip_reason'] = 'Rest'
        assert client.put(endpoint, json=payload).status_code == 200
        assert counts() == (2, 1)
    scale_endpoint = f'/api/habits/{scale}/entries/{today}'
    assert client.put(scale_endpoint, json={'status': 'done', 'value': 0}).status_code == 200
    assert counts() == (2, 2)
    assert client.delete(scale_endpoint).status_code == 204
    assert counts() == (2, 1)

    # Archived habits match the day screen: only recorded cards remain visible.
    assert client.post(f'/api/habits/{scale}/archive').status_code == 200
    assert client.post(f'/api/habits/{completion}/archive').status_code == 200
    assert counts() == (1, 1)
