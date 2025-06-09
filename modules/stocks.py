import requests
import pandas as pd

def fetch_ohlcv(symbol: str, interval: str='1h', limit: int=500):
    """
    symbol — торговая пара, напр. 'BTCUSDT'
    interval — интервал свечей: '1m','5m','1h','1d' и т.д.
    limit — число последних свечей (макс 1000)
    """
    url = 'https://api.binance.com/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    # Преобразуем в DataFrame
    cols = ['OpenTime','Open','High','Low','Close','Volume',
            'CloseTime','QuoteAssetVol','Trades','BuyBaseVol',
            'BuyQuoteVol','Ignore']
    df = pd.DataFrame(data, columns=cols)
    # Конвертируем типы
    df['OpenTime']  = pd.to_datetime(df['OpenTime'], unit='ms')
    df['CloseTime'] = pd.to_datetime(df['CloseTime'], unit='ms')
    for c in ['Open','High','Low','Close','Volume']:
        df[c] = df[c].astype(float)
    return df.set_index('OpenTime')

# Пример:
df = fetch_ohlcv('ETHUSDT', interval='1h', limit=24)
df[['Open','High','Low','Close','Volume']]