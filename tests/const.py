"""Constants of the KEF Connector tests (data of real speakers)."""

from datetime import UTC, datetime

# The user's LS50 Wireless II.
HOST = "192.168.1.20"
HOST_IPV6_LINK_LOCAL = "fe80::8617:15ff:fe00:1"
HOST_IPV6_GLOBAL = "2001:db8::8617:15ff:fe00:1"
NAME = "Gramophone"
MODEL_NAME = "SP4025"
SERIAL = "LSW0123456789ABC"
MAC = "84:17:15:00:00:01"
UNIQUE_ID = "84:17:15:00:00:01"
FIRMWARE = "4.1.192.0x869cad1"
RELEASE_TEXT = "LS50WII_V41192"
SERVICE_NAME = "841715000001@LS50WII._kef-info._tcp.local."
ENTITY_ID = "media_player.gramophone"

# A second speaker (LSX II).
HOST_2 = "192.168.1.47"
NAME_2 = "Salon"
MODEL_NAME_2 = "SP4041"
SERIAL_2 = "LSX2W2104567A1B2"
MAC_2 = "84:17:15:20:1B:C3"
UNIQUE_ID_2 = "84:17:15:20:1b:c3"
FIRMWARE_2 = "3.0.139.12"
ENTITY_ID_2 = "media_player.salon"

POSITION_UPDATED_AT = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)

EQ_PROFILE_V2 = {
    "profileName": "Living room",
    "profileId": "6c3c2d2e-4a0f-4c55-9c39-6f3c7f0e2a10",
    "isExpertMode": True,
    "balance": 0,
    "deskMode": False,
    "deskModeSetting": -3.0,
    "wallMode": False,
    "wallModeSetting": -1.5,
    "phaseCorrection": True,
    "trebleAmount": 0.25,
    "highPassMode": False,
    "highPassModeFreq": 95.0,
    "subwooferPolarity": "normal",
    "subOutLPFreq": 80.0,
    "bassExtension": "standard",
    "subwooferGain": 0.0,
    "subEnableStereo": False,
    "audioPolarity": "normal",
    "isKW1": False,
    "subwooferCount": 1,
    "subwooferPreset": "custom",
    "subwooferOut": False,
    "soundProfile": "default",
    "wallMounted": False,
    "dialogueMode": False,
    "isEqMode": False,
    "wirelessSub": False,
}

# EQ profile of the user's LS50 Wireless II (firmware 4.1.192), KC62 preset.
EQ_PROFILE_LS50WII = {
    "profileName": "",
    "profileId": "",
    "isExpertMode": False,
    "balance": 0,
    "deskMode": False,
    "deskModeSetting": -3.0,
    "wallMode": True,
    "wallModeSetting": -2.5,
    "phaseCorrection": True,
    "trebleAmount": 1.0,
    "highPassMode": False,
    "highPassModeFreq": 70.0,
    "subwooferPolarity": "normal",
    "subOutLPFreq": 45.0,
    "bassExtension": "less",
    "subwooferGain": 0.0,
    "subEnableStereo": False,
    "audioPolarity": "normal",
    "isKW1": False,
    "subwooferCount": 0,
    "subwooferPreset": "kc62",
    "subwooferOut": False,
    "soundProfile": "default",
    "wallMounted": False,
    "dialogueMode": False,
    "isEqMode": False,
    "wirelessSub": False,
}

# EQ profile in indices (v1, LS50 Wireless II before firmware 2.5.74).
EQ_PROFILE_V1 = {
    "profileName": "",
    "profileId": "",
    "isExpertMode": False,
    "dspInfo": {
        "balance": 30,
        "deskMode": False,
        "deskModeSetting": 14,
        "wallMode": False,
        "wallModeSetting": 20,
        "phaseCorrection": True,
        "trebleAmount": 8,
        "highPassMode": False,
        "highPassModeFreq": 9,
        "subwooferPolarity": "normal",
        "subOutLPFreq": 8,
        "bassExtension": "standard",
        "subwooferGain": 10,
        "subEnableStereo": False,
        "audioPolarity": "normal",
        "isKW1": False,
        "subwooferCount": 0,
        "subwooferPreset": "custom",
    },
}

# ``player:player/data`` while Spotify Connect plays a track.
PLAYER_DATA = {
    "state": "playing",
    "status": {"duration": 562000, "playSpeed": 1},
    "trackRoles": {
        "title": "So What",
        "icon": "https://i.scdn.co/image/ab67616d0000b273kindofblue",
        "mediaData": {
            "metaData": {
                "artist": "Miles Davis",
                "album": "Kind of Blue",
                "serviceID": "spotify",
                "live": False,
            },
            "resources": [
                {
                    "duration": 562000,
                    "codec": "vorbis",
                    "sampleFrequency": 44100,
                    "bitsPerSample": 16,
                    "nrAudioChannels": 2,
                    "bitRate": 320000,
                }
            ],
        },
    },
    "controls": {
        "pause": True,
        "next_": True,
        "previous": True,
        "seekTime": True,
        "playMode": {
            "normal": True,
            "repeatOne": True,
            "repeatAll": True,
            "shuffle": True,
            "shuffleRepeatOne": True,
            "shuffleRepeatAll": True,
        },
    },
    "mediaRoles": {"title": "Spotify", "type": "container"},
}
