package com.example.aitourism.controller;

import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.POI;
import com.example.aitourism.mapper.POIMapper;
import com.example.aitourism.service.PriceProxyService;
import com.example.aitourism.util.CityGeoUtil;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import java.time.LocalDate;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 内部工具接口（供 Python Agent 的领域工具调用，对应 Agent 侧 poi.py / price_provider.py）。
 *
 * <p>说明：Agent 的景点搜索工具此前调用 /api/tools/poi 但后端未实现该接口（404），
 * 本次改造补齐，并新增「真实价格」系列接口：
 * <ul>
 *   <li>GET /api/tools/poi            景点列表（含真实门票价，来自 t_poi）</li>
 *   <li>GET /api/tools/city-distance  两城距离（真实坐标库，大交通计价基础）</li>
 *   <li>GET /api/tools/train-price    火车票真实票价（代理聚合数据/极速数据，同步 12306）</li>
 *   <li>GET /api/tools/hotel-price    酒店快照价（t_hotel_price_snapshot）</li>
 * </ul>
 * 所有接口遵循「拿不到就明说」原则：无数据时返回错误码，
 * 由 Agent 侧降级到系数估算并标注「系统估算」，绝不返回伪造价格。
 */
@RestController
@RequestMapping("/api/tools")
@RequiredArgsConstructor
public class ToolsController {

    private final POIMapper poiMapper;
    private final PriceProxyService priceProxyService;

    /**
     * 景点搜索（Agent POI 工具调用）。
     * 返回景点名/城市/坐标/门票价格等，门票价格为景点库真实数据。
     */
    @GetMapping("/poi")
    public BaseResponse<Map<String, Object>> poi(
            @RequestParam String city_name,
            @RequestParam(defaultValue = "10") Integer count) {
        try {
            if (city_name == null || city_name.trim().isEmpty()) {
                return BaseResponse.error(2001, "城市名称不能为空");
            }
            String city = city_name.trim();
            if (city.endsWith("市")) city = city.substring(0, city.length() - 1);
            int limit = (count == null || count <= 0) ? 10 : Math.min(count, 50);
            List<POI> pois = poiMapper.findByCityName(city, limit);
            Map<String, Object> data = new HashMap<>();
            data.put("city_name", city);
            data.put("poi_list", pois);
            return BaseResponse.success(data);
        } catch (RuntimeException e) {
            return BaseResponse.error(5001, "查询景点信息失败: " + e.getMessage());
        }
    }

    /** 两城间直线距离（km，来自真实坐标库 CityGeoUtil） */
    @GetMapping("/city-distance")
    public BaseResponse<Map<String, Object>> cityDistance(
            @RequestParam String origin,
            @RequestParam String dest) {
        Map<String, Object> data = new HashMap<>();
        data.put("origin", origin);
        data.put("dest", dest);
        double[] o = CityGeoUtil.getCoord(origin);
        double[] d = CityGeoUtil.getCoord(dest);
        if (o == null || d == null) {
            data.put("km", null);
            data.put("known", false);
            return BaseResponse.success(data);
        }
        double km = CityGeoUtil.distanceKm(origin, dest);
        data.put("km", Math.round(km * 10.0) / 10.0);
        data.put("known", true);
        return BaseResponse.success(data);
    }

    /**
     * 火车票真实票价（代理聚合数据/极速数据，同步 12306）。
     * 未配置 API Key 时返回 5003，Agent 会自动降级到系数估算。
     */
    @GetMapping("/train-price")
    public BaseResponse<Map<String, Object>> trainPrice(
            @RequestParam String origin,
            @RequestParam String dest,
            @RequestParam(required = false) String date) {
        try {
            if (!priceProxyService.trainApiEnabled()) {
                return BaseResponse.error(5003,
                        "未配置火车票查询 API（price.train.provider/api-key），已降级为票价模型估算");
            }
            String depart = (date == null || date.isBlank()) ? LocalDate.now().toString() : date.trim();
            List<PriceProxyService.SeatQuote> quotes = priceProxyService.trainQuotes(origin, dest, depart);
            if (quotes.isEmpty()) {
                return BaseResponse.error(5004,
                        "未查询到真实票价（可能超出 12306 预售期 14 天或无车次），已降级为票价模型估算");
            }
            Map<String, Object> data = new HashMap<>();
            data.put("origin", origin);
            data.put("dest", dest);
            data.put("date", depart);
            boolean realtime = quotes.stream().anyMatch(q -> q.trainCode() != null && !q.trainCode().isBlank());
            data.put("provider", realtime ? "juhe/jisu(12306同步)" : "12306实爬票价表");
            data.put("as_of", LocalDate.now().toString());
            data.put("quotes", quotes.stream().map(q -> {
                Map<String, Object> m = new LinkedHashMap<>();
                m.put("seat_type", q.seatType());
                m.put("price", q.price());
                if (q.trainCode() != null) m.put("train_code", q.trainCode());
                if (q.departTime() != null) m.put("depart_time", q.departTime());
                return m;
            }).toList());
            return BaseResponse.success(data);
        } catch (RuntimeException e) {
            return BaseResponse.error(5005, "火车票查询失败: " + e.getMessage());
        }
    }

    /**
     * 酒店快照价（t_hotel_price_snapshot）。
     * tier: economy / comfort / premium。无快照数据返回 5006，Agent 降级档次默认价。
     */
    @GetMapping("/hotel-price")
    public BaseResponse<Map<String, Object>> hotelPrice(
            @RequestParam String city,
            @RequestParam(defaultValue = "comfort") String tier) {
        try {
            PriceProxyService.HotelSnapshot snap = priceProxyService.hotelPrice(city, tier);
            if (snap == null) {
                return BaseResponse.error(5006,
                        "暂无「" + city + "」酒店价格快照，已降级为档次参考价（系统估算）");
            }
            Map<String, Object> data = new HashMap<>();
            data.put("city", city);
            data.put("tier", tier);
            data.put("price_per_night", snap.pricePerNight());
            data.put("sample_hotel", snap.sampleHotel());
            data.put("source", snap.source());
            data.put("as_of", snap.collectedDate() != null ? snap.collectedDate().toString() : null);
            return BaseResponse.success(data);
        } catch (RuntimeException e) {
            return BaseResponse.error(5007, "酒店快照查询失败: " + e.getMessage());
        }
    }
}
