package com.example.aitourism.util;

import java.util.HashMap;
import java.util.Map;

/**
 * 中国主要城市坐标与消费等级表（用于交通费用估算）
 */
public class CityGeoUtil {

    // 城市坐标表（经纬度：经度, 纬度）——覆盖景点库中的主要城市
    private static final Map<String, double[]> CITY_COORDS = new HashMap<>();
    // 城市消费等级（1=一般, 2=二线, 3=一线）——影响市内交通单价
    private static final Map<String, Integer> CITY_TIER = new HashMap<>();

    /**
     * 全国城市中心坐标（由 t_poi 各城市景点坐标取中位数生成，见 script/build_city_centers.py）。
     * 硬编码表只覆盖 49 城，景点库却有 389 城，其余城市没有中心点就无法判断
     * 「某个坐标是否属于该城市」——这正是「银川景点被画到西安」这类串城故障无法被拦截的原因。
     * 该表在静态块中从 classpath 的 city_centers.json 载入，硬编码表优先。
     */
    private static final Map<String, double[]> CITY_CENTERS = new HashMap<>();

    static {
        loadCityCenters();
    }

    /** 中国经纬度合理范围，用于剔除 0 值 / 明显越界的坐标 */
    private static boolean coordInChina(double lng, double lat) {
        return lng >= 73.0 && lng <= 136.0 && lat >= 3.0 && lat <= 54.0;
    }

    private static void loadCityCenters() {
        try (java.io.InputStream in = CityGeoUtil.class.getClassLoader()
                .getResourceAsStream("city_centers.json")) {
            if (in == null) return;
            com.fasterxml.jackson.databind.ObjectMapper om =
                    new com.fasterxml.jackson.databind.ObjectMapper();
            com.fasterxml.jackson.databind.JsonNode centers = om.readTree(in).get("centers");
            if (centers == null) return;
            java.util.Iterator<String> it = centers.fieldNames();
            int n = 0;
            while (it.hasNext()) {
                String city = it.next();
                com.fasterxml.jackson.databind.JsonNode v = centers.get(city);
                if (v == null || v.get("lng") == null || v.get("lat") == null) continue;
                double lng = v.get("lng").asDouble();
                double lat = v.get("lat").asDouble();
                if (!coordInChina(lng, lat)) continue;
                CITY_CENTERS.put(city.trim(), new double[]{lng, lat});
                n++;
            }
            System.out.println("[CityGeoUtil] 已载入城市中心表 " + n + " 城");
        } catch (Exception e) {
            System.err.println("[CityGeoUtil] 城市中心表加载失败（不影响硬编码表）: " + e.getMessage());
        }
    }

    static {
        put("北京", 116.407, 39.904, 3);
        put("上海", 121.473, 31.230, 3);
        put("广州", 113.264, 23.129, 3);
        put("深圳", 114.057, 22.543, 3);
        put("杭州", 120.155, 30.274, 2);
        put("成都", 104.066, 30.573, 2);
        put("西安", 108.940, 34.341, 2);
        put("武汉", 114.305, 30.593, 2);
        put("重庆", 106.551, 29.563, 2);
        put("厦门", 118.089, 24.480, 2);
        put("南京", 118.796, 32.060, 2);
        put("苏州", 120.585, 31.299, 2);
        put("天津", 117.200, 39.085, 2);
        put("青岛", 120.383, 36.067, 2);
        put("长沙", 112.939, 28.228, 2);
        put("昆明", 102.833, 24.880, 2);
        put("郑州", 113.625, 34.747, 2);
        put("济南", 117.120, 36.651, 2);
        put("合肥", 117.227, 31.821, 2);
        put("福州", 119.296, 26.074, 2);
        put("三亚", 109.512, 18.253, 2);
        put("桂林", 110.290, 25.274, 1);
        put("丽江", 100.234, 26.872, 1);
        put("大理", 100.184, 25.773, 1);
        put("拉萨", 91.117, 29.657, 1);
        put("西宁", 101.778, 36.617, 1);
        put("兰州", 103.834, 36.061, 1);
        put("贵阳", 106.630, 26.647, 1);
        put("南昌", 115.858, 28.683, 1);
        put("南宁", 108.366, 22.817, 1);
        put("海口", 110.199, 20.044, 1);
        put("太原", 112.549, 37.857, 1);
        put("石家庄", 114.515, 38.043, 1);
        put("沈阳", 123.432, 41.806, 2);
        put("大连", 121.615, 38.914, 2);
        put("哈尔滨", 126.642, 45.803, 1);
        put("长春", 125.324, 43.897, 1);
        put("呼和浩特", 111.750, 40.842, 1);
        put("银川", 106.231, 38.487, 1);
        put("乌鲁木齐", 87.617, 43.793, 1);
        put("香港", 114.169, 22.319, 3);
        put("澳门", 113.544, 22.199, 3);
        put("台北", 121.565, 25.033, 2);
        put("泰安", 117.088, 36.196, 1);
        put("张家界", 110.479, 29.117, 1);
        put("湘西", 109.599, 27.948, 1);
        put("黄山", 118.166, 29.714, 1);
        put("惠州", 114.416, 23.111, 1);
        put("南投", 120.960, 23.840, 1);
    }

    private static void put(String city, double lng, double lat, int tier) {
        CITY_COORDS.put(city, new double[]{lng, lat});
        CITY_TIER.put(city, tier);
    }

    /** 获取城市坐标（硬编码表优先，其次全国城市中心表；都没有返回 null） */
    public static double[] getCoord(String city) {
        if (city == null) return null;
        double[] v = CITY_COORDS.get(city.trim());
        if (v != null) return v;
        return CITY_CENTERS.get(city.trim());
    }

    /**
     * 判断一个坐标是否「远离」指定城市——用于识别串城市的景点坐标。
     *
     * 大模型生成路线时会自带经纬度，但它常常按景点**最出名的同名地点**给坐标：
     * 「回民街」给成西安回民街（108.9,34.3，而行程城市是银川）、
     * 「西湖公园」给成杭州西湖（120.15,30.25，而行程城市是福州），
     * 直接采用会把银川的行程画到西安去。
     *
     * @param maxKm 允许偏离城市中心的最大公里数（跨城景区、郊区景点需要留余量）
     * @return true=疑似串城市；城市中心未知时返回 false（不敢误判）
     */
    public static boolean isFarFromCity(double lng, double lat, String city, double maxKm) {
        if (!coordInChina(lng, lat)) return true;      // 0 值或越界坐标一律视为异常
        double[] c = getCoord(city);
        if (c == null) return false;                   // 不知道城市中心，不做判断
        return haversineKm(c[1], c[0], lat, lng) > maxKm;
    }

    /** 获取城市消费等级（默认 1） */
    public static int getTier(String city) {
        if (city == null) return 1;
        Integer tier = CITY_TIER.get(city.trim());
        return tier != null ? tier : 1;
    }

    /** 坐标库中全部已知城市名（供上下文解析等场景遍历匹配） */
    public static java.util.Set<String> knownCities() {
        return CITY_COORDS.keySet();
    }

    /**
     * 计算两个城市之间的球面距离（公里，Haversine 公式）
     * 任一城市不在表中时返回 -1
     */
    public static double distanceKm(String cityA, String cityB) {
        double[] a = getCoord(cityA);
        double[] b = getCoord(cityB);
        if (a == null || b == null) return -1;
        return haversineKm(a[1], a[0], b[1], b[0]);
    }

    /**
     * 计算两个经纬度点之间的球面距离（公里，Haversine 公式）
     */
    public static double haversineKm(double lat1, double lon1, double lat2, double lon2) {
        double R = 6371.0;
        double dLat = Math.toRadians(lat2 - lat1);
        double dLon = Math.toRadians(lon2 - lon1);
        double a = Math.sin(dLat / 2) * Math.sin(dLat / 2)
                + Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2))
                * Math.sin(dLon / 2) * Math.sin(dLon / 2);
        double c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
        return R * c;
    }

    /** 从行程文本中提取出发城市（"从北京出发"、"北京出发"、"深圳出发"、"北京到西安"等模式） */
    public static String extractOriginCity(String text, String destCity) {
        if (text == null) return null;
        // 模式1：从X出发/从X来/由X / X出发（可省略"从"字，如"深圳出发"）
        java.util.regex.Matcher m1 = java.util.regex.Pattern
                .compile("(?:从|由|自)?([\\u4e00-\\u9fa5]{2,4})(?:出发|过来|来|启程|动身)").matcher(text);
        while (m1.find()) {
            String city = m1.group(1);
            if (getCoord(city) != null && (destCity == null || !city.contains(destCity))) {
                return city;
            }
        }
        // 模式2：X到Y / X去Y / X→Y / X-Y（两地名模式）
        if (destCity != null && !destCity.isEmpty()) {
            java.util.regex.Matcher m2 = java.util.regex.Pattern
                    .compile("([\\u4e00-\\u9fa5]{2,4})(?:到|去|前往|飞往|至)([\\u4e00-\\u9fa5]{2,4})").matcher(text);
            while (m2.find()) {
                String from = m2.group(1);
                String to = m2.group(2);
                if (to.contains(destCity) && getCoord(from) != null && !from.equals(destCity)) {
                    return from;
                }
            }
        }
        return null;
    }
}
