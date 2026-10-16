def test_hardware_settings_default_audio_volume_is_full(client) -> None:
    response = client.get("/api/hardware/settings", params={"userId": "alexey"})

    assert response.status_code == 200
    assert response.json()["common"]["signalVolume"] == "100%"