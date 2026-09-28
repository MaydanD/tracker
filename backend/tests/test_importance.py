"""Importance is independent versioned metadata; weight keeps its old meaning."""
from datetime import timedelta
import pytest
from app.domain.habits import coerce_importance
from app.domain.errors import InvalidImportanceError
from tests.helpers import FrozenClock, habit_payload

@pytest.mark.parametrize('weight', [1, 2, 3])
@pytest.mark.parametrize('importance', ['low', 'normal', 'high'])
def test_fields_are_independent(client, health_area, weight, importance):
    payload = habit_payload(area_id=health_area['id'], weight=weight)
    payload['importance'] = importance
    result = client.post('/api/habits', json=payload)
    assert result.status_code == 201, result.text
    assert result.json()['weight'] == weight
    assert result.json()['importance'] == importance

@pytest.mark.parametrize('value', ['', 'urgent', 0, 1, 2, 3, 4, True, None, []])
def test_invalid_importance(value):
    with pytest.raises(InvalidImportanceError):
        coerce_importance(value)

@pytest.mark.parametrize('weight', [1, 2, 3])
def test_old_clients_default_to_normal(client, health_area, weight):
    result = client.post('/api/habits', json=habit_payload(area_id=health_area['id'], weight=weight)).json()
    assert result['importance'] == 'normal'
    assert result['weight'] == weight

def test_version_history_and_score_stay_independent(client, app, health_area):
    today = app.state.clock.today()
    payload = {**habit_payload(area_id=health_area['id'], weight=3), 'importance': 'low'}
    habit_id = client.post('/api/habits', json=payload).json()['id']
    client.put(f'/api/habits/{habit_id}/entries/{today}', json={'status': 'done'})
    before = client.get(f'/api/progress/days/{today}').json()['day']
    app.state.clock = FrozenClock(today + timedelta(days=1))
    changed = client.put(f'/api/habits/{habit_id}', json={**payload, 'importance': 'high'})
    assert changed.status_code == 200, changed.text
    history = client.get(f'/api/habits/{habit_id}/versions').json()
    assert [v['importance'] for v in history] == ['high', 'low']
    assert [v['weight'] for v in history] == [3, 3]
    assert client.get(f'/api/progress/days/{today}').json()['day'] == before
