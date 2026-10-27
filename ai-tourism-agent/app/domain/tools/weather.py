"""天气预报工具"""
import os
import time
from typing import Optional, Tuple

import httpx
import jwt
from functools import lru_cache
from loguru import logger
from langchain.tools import tool
from app.config import settings

# 地理编码 API
ENCODE_API_URL = "http://api.openweathermap.org/geo/1.0/direct"
# Open-Meteo 预报 API（免密钥）
OPEN_METEO_API_URL = "https://api.open-meteo.com/v1/forecast"
# Open-Meteo 地理编码 API（免密钥，作为首选地理编码方案）
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
# 高德天气 API（国内覆盖最佳，与地图/票价同一套 Key）
AMAP_WEATHER_URL = "https://restapi.amap.com/v3/weather/weatherInfo"

# 本地城市坐标兜底表：仅在联网地理编码全部不可用时使用。
# 键为去掉「市/区/县」后缀的城市名，值为 (纬度, 经度)。
# 用途：受限网络（如内网代理只放行部分域名）下仍能取到天气。
_CITY_COORDS_FALLBACK = {
    # 直辖市
    "北京": (39.9042, 116.4074), "上海": (31.2304, 121.4737),
    "天津": (39.3434, 117.3616), "重庆": (29.5630, 106.5516),
    # 省会 / 首府
    "石家庄": (38.0428, 114.5149), "太原": (37.8706, 112.5489),
    "呼和浩特": (40.8426, 111.7492), "沈阳": (41.8057, 123.4315),
    "长春": (43.8171, 125.3235), "哈尔滨": (45.8038, 126.5349),
    "南京": (32.0603, 118.7969), "杭州": (30.2741, 120.1551),
    "合肥": (31.8206, 117.2272), "福州": (26.0745, 119.2965),
    "南昌": (28.6820, 115.8579), "济南": (36.6512, 117.1201),
    "郑州": (34.7466, 113.6254), "武汉": (30.5928, 114.3055),
    "长沙": (28.2282, 112.9388), "广州": (23.1291, 113.2644),
    "南宁": (22.8170, 108.3665), "海口": (20.0444, 110.1999),
    "成都": (30.5728, 104.0668), "贵阳": (26.6470, 106.6302),
    "昆明": (25.0389, 102.7183), "拉萨": (29.6500, 91.1000),
    "西安": (34.3416, 108.9398), "兰州": (36.0611, 103.8343),
    "西宁": (36.6171, 101.7782), "银川": (38.4872, 106.2309),
    "乌鲁木齐": (43.8256, 87.6168),
    # 热门旅游 / 重点城市
    "深圳": (22.5431, 114.0579), "苏州": (31.2989, 120.5853),
    "无锡": (31.4912, 120.3119), "宁波": (29.8683, 121.5440),
    "温州": (27.9938, 120.6994), "厦门": (24.4798, 118.0894),
    "青岛": (36.0671, 120.3826), "大连": (38.9140, 121.6147),
    "烟台": (37.4638, 121.4479), "威海": (37.5128, 122.1201),
    "三亚": (18.2528, 109.5119), "桂林": (25.2736, 110.2900),
    "阳朔": (24.7785, 110.4966), "丽江": (26.8721, 100.2299),
    "大理": (25.6065, 100.2676), "香格里拉": (27.8297, 99.7067),
    "西双版纳": (22.0017, 100.7972), "张家界": (29.1170, 110.4791),
    "黄山": (29.7147, 118.3376), "九寨沟": (33.2600, 103.9200),
    "峨眉山": (29.6011, 103.4844), "都江堰": (30.9881, 103.6468),
    "乐山": (29.5521, 103.7656), "敦煌": (40.1421, 94.6618),
    "嘉峪关": (39.7719, 98.2900), "张掖": (38.9257, 100.4498),
    "吐鲁番": (42.9476, 89.1841), "喀什": (39.4677, 75.9938),
    "伊宁": (43.9161, 81.3240), "呼伦贝尔": (49.2116, 119.7658),
    "满洲里": (49.5978, 117.3787), "漠河": (52.9704, 122.5388),
    "延吉": (42.9048, 129.5091), "丹东": (40.0006, 124.3547),
    "洛阳": (34.6197, 112.4540), "开封": (34.7971, 114.3075),
    "平遥": (37.1892, 112.1761), "大同": (40.0768, 113.3001),
    "延安": (36.5853, 109.4898), "宝鸡": (34.3610, 107.2373),
    "天水": (34.5809, 105.7249), "扬州": (32.3942, 119.4129),
    "徐州": (34.2058, 117.2848), "常州": (31.8107, 119.9740),
    "南通": (31.9802, 120.8943), "连云港": (34.5967, 119.2216),
    "绍兴": (30.0024, 120.5810), "义乌": (29.3069, 120.0752),
    "嘉兴": (30.7522, 120.7500), "湖州": (30.8703, 120.0933),
    "台州": (28.6564, 121.4207), "金华": (29.0784, 119.6474),
    "舟山": (29.9853, 122.2072), "普陀山": (30.0100, 122.3900),
    "芜湖": (31.3526, 118.4331), "蚌埠": (32.9155, 117.3894),
    "安庆": (30.5433, 117.0631), "泉州": (24.8741, 118.6757),
    "武夷山": (27.7566, 118.0353), "婺源": (29.2480, 117.8617),
    "景德镇": (29.2688, 117.1784), "赣州": (25.8310, 114.9350),
    "珠海": (22.2707, 113.5767), "佛山": (23.0218, 113.1219),
    "东莞": (23.0207, 113.7518), "中山": (22.5170, 113.3928),
    "惠州": (23.1115, 114.4162), "汕头": (23.3535, 116.6820),
    "湛江": (21.2707, 110.3594), "潮州": (23.6567, 116.6226),
    "北海": (21.4733, 109.1194), "宜昌": (30.6919, 111.2865),
    "襄阳": (32.0090, 112.1224), "岳阳": (29.3571, 113.1289),
    "常德": (29.0316, 111.6987), "衡阳": (26.8938, 112.5720),
    "遵义": (27.7256, 106.9274), "安顺": (26.2456, 105.9322),
    "泸州": (28.8717, 105.4433), "宜宾": (28.7513, 104.6308),
    "绵阳": (31.4679, 104.6796), "曲靖": (25.4901, 103.7962),
    "腾冲": (25.0203, 98.4903), "秦皇岛": (39.9354, 119.6005),
    "承德": (40.9515, 117.9634),
}


# Open-Meteo 地理编码熔断状态：受限网络下该域名可能不可达，
# 连续失败达阈值后在冷却期内直接跳过，避免每次调用都白等一个超时。
_GEOCODE_FAIL_STREAK = 0
_GEOCODE_SKIP_UNTIL = 0.0
_GEOCODE_FAIL_THRESHOLD = 2
_GEOCODE_COOLDOWN_SECONDS = 300


@tool
def weather_forecast(city_name: str, day_count: int = 7) -> str:
    """
    根据城市名获取未来若干天的逐天天气预报，天数范围1-16
    
    Args:
        city_name: 城市名称，例如: 北京 / Shanghai / New York
        day_count: 要返回的预测天数，范围1-16
    
    Returns:
        天气预报 JSON 字符串
    """
    logger.info(f"调用天气工具，城市: {city_name}, 天数: {day_count}, 提供商: {settings.weather_provider}")
    
    try:
        # 参数验证
        if not city_name or not city_name.strip():
            return "城市名称不能为空"
        
        if day_count < 1:
            day_count = 1
        if day_count > 16:
            day_count = 16
        
        # 根据配置选择天气服务提供商
        provider = (settings.weather_provider or "amap").lower()
        if provider == "amap" and settings.amap_web_api_key:
            result = _fetch_weather_amap(city_name, day_count)
            # 高德查询失败（网络/限流）时回退 Open-Meteo，保证功能不中断
            if "失败" not in result and "错误" not in result:
                return result
            logger.warning(f"高德天气查询异常，回退 Open-Meteo: {result[:80]}")
            return _fetch_weather_openweather(city_name, day_count)
        if provider == "qweather":
            return _fetch_weather_qweather(city_name, day_count)
        else:
            # 默认使用 OpenWeather + Open-Meteo
            return _fetch_weather_openweather(city_name, day_count)
    
    except Exception as e:
        logger.error(f"获取天气数据异常: {e}", exc_info=True)
        return "获取天气数据时发生错误，请忽略此错误"


def _fetch_weather_openweather(city_name: str, day_count: int) -> str:
    """使用 OpenWeather + Open-Meteo API 获取天气"""
    # 1. 地理编码获取经纬度
    lat, lon = _get_city_coordinates(city_name)
    if lat is None or lon is None:
        return "获取城市经纬度失败，请检查城市名称"
    
    # 2. 调用 Open-Meteo API
    from datetime import date, timedelta
    today = date.today() + timedelta(1)
    end_date = today + timedelta(days=day_count - 1)
    
    url = (
        f"{OPEN_METEO_API_URL}?"
        f"latitude={lat}&longitude={lon}&"
        f"start_date={today}&end_date={end_date}&"
        f"daily=temperature_2m_min,temperature_2m_max,temperature_2m_mean,"
        f"precipitation_sum,snowfall_sum,windspeed_10m_max,windgusts_10m_max,winddirection_10m_dominant&"
        f"timezone=auto"
    )
    
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url)
        if not response.is_success:
            logger.error(f"Open-Meteo API 调用失败: {response.status_code}")
            return "暂时无法获取天气数据，请忽略此错误"
        
        data = response.json()
        daily = data.get("daily", {})
        
        # 3. 格式化返回结果
        result = []
        times = daily.get("time", [])
        t_min = daily.get("temperature_2m_min", [])
        t_max = daily.get("temperature_2m_max", [])
        t_mean = daily.get("temperature_2m_mean", [])
        precip = daily.get("precipitation_sum", [])
        
        for i in range(len(times)):
            day_weather = {
                "日期": times[i],
                "最低温(℃)": round(t_min[i], 1) if i < len(t_min) else 0,
                "最高温(℃)": round(t_max[i], 1) if i < len(t_max) else 0,
                "平均温(℃)": round(t_mean[i], 1) if i < len(t_mean) else 0,
                "降水量(mm)": round(precip[i], 1) if i < len(precip) else 0,
            }
            result.append(day_weather)
        
        import json
        return json.dumps(result, ensure_ascii=False, indent=2)


def _fetch_weather_amap(city_name: str, day_count: int) -> str:
    """使用高德天气 API 获取天气预报（extensions=all，未来 4 天）。

    选型理由：高德天气对国内城市覆盖最全（含区县），与地图、票价共用同一套 Key，
    返回字段含白天/夜间分开的天气与风力，比 Open-Meteo 更贴近国内用户体感。
    """
    import json as _json

    city = city_name.strip()
    if city.endswith("市"):
        city = city[:-1]
    try:
        params = {
            "key": settings.amap_web_api_key,
            "city": city,
            "extensions": "all"
        }
        with httpx.Client(timeout=10.0, trust_env=False) as client:
            response = client.get(AMAP_WEATHER_URL, params=params)
            if not response.is_success:
                logger.error(f"高德天气 API 调用失败: HTTP {response.status_code}")
                return "获取天气数据失败，请忽略此错误"
            data = response.json()
    except Exception as e:
        logger.error(f"高德天气 API 异常: {e}")
        return "获取天气数据失败，请忽略此错误"

    if data.get("status") != "1":
        logger.warning(f"高德天气返回异常: {data.get('info')} (city={city})")
        return "获取天气数据失败，请忽略此错误"

    forecasts = data.get("forecasts") or []
    if not forecasts:
        return "获取天气数据失败，请忽略此错误"
    casts = forecasts[0].get("casts") or []
    if not casts:
        return "获取天气数据失败，请忽略此错误"

    result = []
    for i, c in enumerate(casts):
        if i >= day_count:
            break
        result.append({
            "日期": c.get("date"),
            "星期": c.get("week"),
            "白天天气": c.get("dayweather"),
            "夜间天气": c.get("nightweather"),
            "最高温(℃)": c.get("daytemp"),
            "最低温(℃)": c.get("nighttemp"),
            "白天风力": c.get("daywindpower")
        })
    # 实况天气作为首日补充
    lives = data.get("lives") or []
    if lives and result:
        live = lives[0]
        result[0]["当前天气"] = live.get("weather")
        result[0]["当前温度(℃)"] = live.get("temperature")
        result[0]["当前湿度(%)"] = live.get("humidity")
    return _json.dumps(result, ensure_ascii=False, indent=2)


def _fetch_weather_qweather(city_name: str, day_count: int) -> str:
    """使用和风天气 API 获取天气"""
    jwt_token = _generate_qweather_jwt()
    if not jwt_token:
        logger.warning("和风天气 JWT 未正确配置或生成失败，回退到 OpenWeather")
        return _fetch_weather_openweather(city_name, day_count)
    
    try:
        # 1. 获取城市 LocationID（和风天气需要）
        location_id = _get_qweather_location_id(city_name, jwt_token)
        if not location_id:
            logger.warning(f"和风天气未找到城市 {city_name}，回退到 OpenWeather")
            return _fetch_weather_openweather(city_name, day_count)
        
        # 2. 调用和风天气 API（最多支持 15 天预报）
        day_count+=1
        if day_count <= 3:
            period = 3
        elif day_count <= 7:
            period = 7
        elif day_count <= 10:
            period = 10
        else:
            period = 15

        base_url = _get_qweather_base_url()
        url = f"{base_url}/v7/weather/{period}d"
        params = {
            "location": location_id,
            "lang": "zh"
        }
        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }
        
        with httpx.Client(timeout=10.0, headers=headers) as client:
            response = client.get(url, params=params)
            if not response.is_success:
                logger.error(f"和风天气 API 调用失败: {response.status_code}")
                logger.warning("回退到 OpenWeather")
                return _fetch_weather_openweather(city_name, day_count)
            
            data = response.json()
            if data.get("code") != "200":
                logger.error(f"和风天气 API 返回错误: {data.get('code')}, {data.get('msg')}")
                logger.warning("回退到 OpenWeather")
                return _fetch_weather_openweather(city_name, day_count)
            
            # 3. 格式化返回结果
            daily = data.get("daily", [])
            result = []

            # QWeather 返回的 daily 通常包含「今天 + 未来几天」
            # 业务上我们希望与 Open-Meteo 行为对齐：从“明天”开始算 day_count 天
            # 因此这里优先跳过索引 0（今天），从索引 1 开始取 day_count 条
            start_idx = 1 if len(daily) > 1 else 0

            for day_data in daily[start_idx:day_count]:
                day_weather = {
                    "日期": day_data.get("fxDate", ""),
                    "最低温(℃)": float(day_data.get("tempMin", 0)),
                    "最高温(℃)": float(day_data.get("tempMax", 0)),
                    "平均温(℃)": (float(day_data.get("tempMin", 0)) + float(day_data.get("tempMax", 0))) / 2,
                    "降水量(mm)": float(day_data.get("precip", 0)),
                    "天气": day_data.get("textDay", ""),
                    "风向": day_data.get("windDirDay", ""),
                    "风力": day_data.get("windScaleDay", ""),
                }
                result.append(day_weather)
            
            import json
            return json.dumps(result, ensure_ascii=False, indent=2)
    
    except Exception as e:
        logger.error(f"和风天气 API 调用异常: {e}", exc_info=True)
        logger.warning("回退到 OpenWeather")
        return _fetch_weather_openweather(city_name, day_count)


def _get_qweather_location_id(city_name: str, jwt_token: str) -> Optional[str]:
    """获取和风天气的城市 LocationID"""
    try:
        base_url = _get_qweather_base_url()
        url = f"{base_url}/geo/v2/city/lookup"
        params = {
            "location": city_name,
        }
        headers = {
            "Authorization": f"Bearer {jwt_token}"
        }
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params, headers=headers)
            if not response.is_success:
                logger.error(f"和风天气地理编码 API 调用失败: {response.status_code}")
                return None
            
            data = response.json()
            if data.get("code") != "200":
                logger.warning(f"和风天气未找到城市: {city_name}, code: {data.get('code')}")
                return None
            
            locations = data.get("location", [])
            if not locations or len(locations) == 0:
                logger.warning(f"和风天气未找到城市: {city_name}")
                return None
            
            location_id = locations[0].get("id")
            logger.info(f"和风天气找到城市 {city_name} 的 LocationID: {location_id}")
            return location_id
    
    except Exception as e:
        logger.error(f"获取和风天气 LocationID 异常: {e}", exc_info=True)
        return None


def _get_qweather_base_url() -> str:
    """
    获取和风天气基础域名：
    - 优先使用环境变量 QWEATHER_API_HOST（settings.qweather_api_host）
    - 未配置时回退到官方域名 https://devapi.qweather.com
    """
    host = (settings.qweather_api_host or "").strip()
    if not host:
        return "https://devapi.qweather.com"
    # 如果用户只配置了主机名而未带协议，默认加上 https://
    if host.startswith("http://") or host.startswith("https://"):
        return host.rstrip("/")
    return f"https://{host.rstrip('/')}"


@lru_cache()
def _load_qweather_private_key() -> Optional[str]:
    """加载和风天气 JWT 私钥 PEM 内容"""
    path = (settings.qweather_jwt_private_key_path or "").strip()
    if not path:
        logger.warning("和风天气 JWT 私钥路径未配置（QWEATHER_JWT_PRIVATE_KEY_PATH），无法生成 JWT")
        return None
    
    # 支持相对路径：相对于当前工作目录
    if not os.path.isabs(path):
        path = os.path.join(os.getcwd(), path)
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            key = f.read()
            return key
    except FileNotFoundError:
        logger.error(f"和风天气 JWT 私钥文件未找到: {path}")
    except Exception as e:
        logger.error(f"加载和风天气 JWT 私钥失败: {e}", exc_info=True)
    return None


def _generate_qweather_jwt() -> Optional[str]:
    """根据配置生成和风天气所需的 JWT（EdDSA）"""
    project_id = (settings.qweather_jwt_project_id or "").strip()
    key_id = (settings.qweather_jwt_key_id or "").strip()
    private_key = _load_qweather_private_key()
    
    if not project_id or not key_id or not private_key:
        logger.warning(
            "和风天气 JWT 配置不完整："
            f"project_id={bool(project_id)}, key_id={bool(key_id)}, private_key={bool(private_key)}"
        )
        return None
    
    try:
        now = int(time.time())
        payload = {
            "iat": now - 30,
            "exp": now + 900,
            "sub": project_id,
        }
        headers = {
            "kid": key_id,
        }
        token = jwt.encode(payload, private_key, algorithm="EdDSA", headers=headers)
        return token
    except Exception as e:
        logger.error(f"生成和风天气 JWT 失败: {e}", exc_info=True)
        return None


def _get_city_coordinates(city_name: str) -> Tuple[Optional[float], Optional[float]]:
    """
    获取城市经纬度。按以下优先级逐级降级，任一级成功即返回：

    1. Open-Meteo 地理编码 —— 免密钥、覆盖全球，首选；
    2. OpenWeather 地理编码 —— 仅在配置了 OPENWEATHER_API_KEY 时尝试（向后兼容）；
    3. 本地城市坐标表 —— 受限网络（代理只放行部分域名）或离线时兜底。

    前两级都是联网实时方案；第三级保证天气功能不因网络策略而整体不可用。
    """
    cleaned = (city_name or "").strip().rstrip("市区县")
    if not cleaned:
        return None, None

    # 1. Open-Meteo 地理编码（免密钥）
    lat, lon = _geocode_open_meteo(cleaned)
    if lat is not None and lon is not None:
        logger.info(f"Open-Meteo 地理编码 {cleaned} -> ({lat}, {lon})")
        return lat, lon

    # 2. OpenWeather 地理编码（需密钥，向后兼容）
    if settings.openweather_api_key:
        lat, lon = _geocode_openweather(cleaned, settings.openweather_api_key)
        if lat is not None and lon is not None:
            logger.info(f"OpenWeather 地理编码 {cleaned} -> ({lat}, {lon})")
            return lat, lon

    # 3. 本地坐标表兜底
    if cleaned in _CITY_COORDS_FALLBACK:
        lat, lon = _CITY_COORDS_FALLBACK[cleaned]
        logger.warning(f"联网地理编码不可用，本地坐标表兜底 {cleaned} -> ({lat}, {lon})")
        return lat, lon

    logger.warning(f"无法解析城市坐标: {city_name}")
    return None, None


def _geocode_open_meteo(city_name: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Open-Meteo 地理编码（免密钥）。失败时返回 (None, None)，交由上层降级。

    带熔断：受限网络下该域名可能不可达，每次调用都要白等一个超时（实测约 8-9 秒）。
    连续失败达阈值后进入冷却期，冷却期内直接跳过，不再尝试。
    """
    global _GEOCODE_FAIL_STREAK, _GEOCODE_SKIP_UNTIL

    now = time.time()
    if now < _GEOCODE_SKIP_UNTIL:
        return None, None  # 熔断中，静默跳过

    try:
        params = {"name": city_name, "count": 1, "language": "zh", "format": "json"}
        with httpx.Client(timeout=5.0) as client:
            response = client.get(OPEN_METEO_GEOCODING_URL, params=params)
        if not response.is_success:
            logger.warning(f"Open-Meteo 地理编码返回 {response.status_code}，将走降级方案")
            _trip_geocode_breaker()
            return None, None
        results = response.json().get("results") or []
        if not results:
            # 请求成功但确实没这个城市：属于正常业务结果，不计入熔断
            logger.warning(f"Open-Meteo 未找到城市: {city_name}")
            _GEOCODE_FAIL_STREAK = 0
            return None, None
        _GEOCODE_FAIL_STREAK = 0
        top = results[0]
        return top.get("latitude"), top.get("longitude")
    except Exception as e:
        logger.warning(f"Open-Meteo 地理编码异常（将走降级方案）: {e}")
        _trip_geocode_breaker()
        return None, None


def _trip_geocode_breaker() -> None:
    """累计地理编码失败次数，达阈值则进入冷却期。"""
    global _GEOCODE_FAIL_STREAK, _GEOCODE_SKIP_UNTIL
    _GEOCODE_FAIL_STREAK += 1
    if _GEOCODE_FAIL_STREAK >= _GEOCODE_FAIL_THRESHOLD:
        _GEOCODE_SKIP_UNTIL = time.time() + _GEOCODE_COOLDOWN_SECONDS
        logger.warning(
            f"Open-Meteo 地理编码连续失败 {_GEOCODE_FAIL_STREAK} 次，"
            f"熔断 {_GEOCODE_COOLDOWN_SECONDS}s 内直接使用本地坐标表"
        )
        _GEOCODE_FAIL_STREAK = 0


def _geocode_openweather(city_name: str, api_key: str) -> Tuple[Optional[float], Optional[float]]:
    """OpenWeather 地理编码（需密钥）。失败时返回 (None, None)。"""
    try:
        url = f"{ENCODE_API_URL}?q={city_name}&limit=1&appid={api_key}"
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
        if not response.is_success:
            logger.warning(f"OpenWeather 地理编码返回 {response.status_code}")
            return None, None
        data = response.json()
        if not data:
            logger.warning(f"OpenWeather 未找到城市: {city_name}")
            return None, None
        return data[0].get("lat"), data[0].get("lon")
    except Exception as e:
        logger.warning(f"OpenWeather 地理编码异常: {e}")
        return None, None

