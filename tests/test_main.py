import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch

from main import app, MessageListener
from model import ReclaimStateResponse, BoostStatus

# Mock ReclaimStateResponse objects
STATE_SUCCESS = ReclaimStateResponse(
    mode="Mode 1: 24H",
    pump=True,
    case=50.0,
    water=60.0,
    outlet=1.0,
    inlet=2.0,
    discharge=3.0,
    suction=4.0,
    evaporator=5.0,
    ambient=6.0,
    compspeed=7,
    waterspeed=8,
    fanspeed=9,
    power=10,
    current=11.0,
    hours=12.0,
    starts=13.0,
    boost=False
)

BOOST_ON_INITIAL = ReclaimStateResponse(
    mode="Mode 1: 24H",
    pump=False,
    case=50.0,
    water=50.0,
    outlet=1.0,
    inlet=2.0,
    discharge=3.0,
    suction=4.0,
    evaporator=5.0,
    ambient=6.0,
    compspeed=7,
    waterspeed=8,
    fanspeed=9,
    power=10,
    current=11.0,
    hours=12.0,
    starts=13.0,
    boost=False
)

BOOST_ON_FINAL = ReclaimStateResponse(
    mode="Mode 1: 24H",
    pump=False,
    case=50.0,
    water=50.0,
    outlet=1.0,
    inlet=2.0,
    discharge=3.0,
    suction=4.0,
    evaporator=5.0,
    ambient=6.0,
    compspeed=7,
    waterspeed=8,
    fanspeed=9,
    power=10,
    current=11.0,
    hours=12.0,
    starts=13.0,
    boost=True
)

BOOST_OFF_INITIAL = ReclaimStateResponse(
    mode="Mode 1: 24H",
    pump=False,
    case=50.0,
    water=50.0,
    outlet=1.0,
    inlet=2.0,
    discharge=3.0,
    suction=4.0,
    evaporator=5.0,
    ambient=6.0,
    compspeed=7,
    waterspeed=8,
    fanspeed=9,
    power=10,
    current=11.0,
    hours=12.0,
    starts=13.0,
    boost=True
)

BOOST_OFF_FINAL = ReclaimStateResponse(
    mode="Mode 1: 24H",
    pump=False,
    case=50.0,
    water=50.0,
    outlet=1.0,
    inlet=2.0,
    discharge=3.0,
    suction=4.0,
    evaporator=5.0,
    ambient=6.0,
    compspeed=7,
    waterspeed=8,
    fanspeed=9,
    power=10,
    current=11.0,
    hours=12.0,
    starts=13.0,
    boost=False
)

@pytest.fixture
def client():
    app.state.reclaimv2 = MagicMock()
    app.state.listener = MessageListener()
    return TestClient(app)

@patch('model.ReclaimStateResponse.from_state')
def test_state_success(mock_from_state, client):
    # Arrange
    mock_from_state.return_value = STATE_SUCCESS
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)

    # Act
    response = client.get("/state")

    # Assert
    assert response.status_code == 200
    json = response.json()
    assert json['mode'] == "Mode 1: 24H"
    assert json['pump'] is True
    assert json['case'] == 50
    assert json['water'] == 60

def test_state_failure(client):
    # Arrange
    app.state.reclaimv2.request_update = AsyncMock(return_value=False)

    # Act
    response = client.get("/state")

    # Assert
    assert response.status_code == 204

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_success(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_ON_INITIAL, BOOST_ON_FINAL]
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 200
    app.state.reclaimv2.set_value.assert_called_once_with("boost", True)

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_already_on(mock_from_state, client):
    # Arrange
    mock_from_state.return_value = BOOST_ON_FINAL
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 409
    json = response.json()
    assert json['detail'] == 'Boost was already ON; will not turn boost ON.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_off_success(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_OFF_INITIAL, BOOST_OFF_FINAL]
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/off")

    # Assert
    assert response.status_code == 200
    app.state.reclaimv2.set_value.assert_called_once_with("boost", False)

@patch('model.ReclaimStateResponse.from_state')
def test_boost_off_failure_already_off(mock_from_state, client):
    # Arrange
    mock_from_state.return_value = BOOST_OFF_FINAL
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)

    # Act
    response = client.post("/boost/off")

    # Assert
    assert response.status_code == 409
    json = response.json()
    assert json['detail'] == 'Boost was already OFF; will not turn boost OFF.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_off_failure_get_updated_state(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_OFF_INITIAL, None]
    app.state.reclaimv2.request_update = AsyncMock(side_effect=[True, False])
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/off")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to get updated state; boost status uncertain.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_off_failure_turn_off_boost(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_OFF_INITIAL, BOOST_OFF_INITIAL]
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/off")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to turn OFF boost.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_off_failure_get_current_state(mock_from_state, client):
    # Arrange
    app.state.reclaimv2.request_update = AsyncMock(return_value=False)

    # Act
    response = client.post("/boost/off")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to get current state; will not turn boost OFF.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_get_updated_state(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_ON_INITIAL, None]
    app.state.reclaimv2.request_update = AsyncMock(side_effect=[True, False])
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to get updated state; boost status uncertain.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_turn_on_boost(mock_from_state, client):
    # Arrange
    mock_from_state.side_effect = [BOOST_ON_INITIAL, BOOST_ON_INITIAL]
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)
    app.state.reclaimv2.set_value = AsyncMock()

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to turn ON boost.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_get_current_state(mock_from_state, client):
    # Arrange
    app.state.reclaimv2.request_update = AsyncMock(return_value=False)

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 500
    json = response.json()
    assert json['detail'] == 'Failed to get current state; will not turn boost ON.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_heater_running(mock_from_state, client):
    # Arrange
    mock_response = ReclaimStateResponse(
        mode="Mode 1: 24H",
        pump=True,
        case=50.0,
        water=50.0,
        outlet=1.0,
        inlet=2.0,
        discharge=3.0,
        suction=4.0,
        evaporator=5.0,
        ambient=6.0,
        compspeed=7,
        waterspeed=8,
        fanspeed=9,
        power=10,
        current=11.0,
        hours=12.0,
        starts=13.0,
        boost=False
    )
    mock_from_state.return_value = mock_response
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 409
    json = response.json()
    assert json['detail'] == 'Heater is already running (non-boost); will not turn on boost.'

@patch('model.ReclaimStateResponse.from_state')
def test_boost_on_failure_water_temp_high(mock_from_state, client):
    # Arrange
    mock_response = ReclaimStateResponse(
        mode="Mode 1: 24H",
        pump=False,
        case=50.0,
        water=56.0,
        outlet=1.0,
        inlet=2.0,
        discharge=3.0,
        suction=4.0,
        evaporator=5.0,
        ambient=6.0,
        compspeed=7,
        waterspeed=8,
        fanspeed=9,
        power=10,
        current=11.0,
        hours=12.0,
        starts=13.0,
        boost=False
    )
    mock_from_state.return_value = mock_response
    app.state.reclaimv2.request_update = AsyncMock(return_value=True)

    # Act
    response = client.post("/boost/on")

    # Assert
    assert response.status_code == 409
    json = response.json()
    assert json['detail'] == 'Water temperature is over 55C; will not turn on boost.'
