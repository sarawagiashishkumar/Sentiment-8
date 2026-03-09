FNO_CONTRACTS = [
    {
        "script": "NIFTY10MAR26500CE",
        "underlying": "NIFTY",
        "expiry": "2026-03-10",
        "strike": 26500,
        "option_type": "CE",
        "exchange": "NFO",
        "lot_size": 65,
    },
    {
        "script": "NIFTY10MAR26500PE",
        "underlying": "NIFTY",
        "expiry": "2026-03-10",
        "strike": 26500,
        "option_type": "PE",
        "exchange": "NFO",
        "lot_size": 65,
    },
    {
        "script": "BANKNIFTY10MAR47000CE",
        "underlying": "BANKNIFTY",
        "expiry": "2026-03-10",
        "strike": 47000,
        "option_type": "CE",
        "exchange": "NFO",
        "lot_size": 30,
    },
    {
        "script": "BANKNIFTY10MAR47000PE",
        "underlying": "BANKNIFTY",
        "expiry": "2026-03-10",
        "strike": 47000,
        "option_type": "PE",
        "exchange": "NFO",
        "lot_size": 30,
    },
    {
        "script": "RELIANCE10MAR3000CE",
        "underlying": "RELIANCE",
        "expiry": "2026-03-10",
        "strike": 3000,
        "option_type": "CE",
        "exchange": "NFO",
        "lot_size": 250,
    },
    {
        "script": "RELIANCE10MAR3000PE",
        "underlying": "RELIANCE",
        "expiry": "2026-03-10",
        "strike": 3000,
        "option_type": "PE",
        "exchange": "NFO",
        "lot_size": 250,
    },
    {
        "script": "BDL10MAR120CE",
        "underlying": "BDL",
        "expiry": "2026-03-10",
        "strike": 120,
        "option_type": "CE",
        "exchange": "NFO",
        "lot_size": 1350,
    },
    {
        "script": "BDL10MAR120PE",
        "underlying": "BDL",
        "expiry": "2026-03-10",
        "strike": 120,
        "option_type": "PE",
        "exchange": "NFO",
        "lot_size": 1350,
    },
]


def get_fno_contract(script: str) -> dict | None:
    for contract in FNO_CONTRACTS:
        if contract["script"] == script:
            return contract
    return None
