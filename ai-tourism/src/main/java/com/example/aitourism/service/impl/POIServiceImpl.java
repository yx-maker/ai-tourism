package com.example.aitourism.service.impl;

import com.example.aitourism.entity.POI;
import com.example.aitourism.mapper.POIMapper;
import com.example.aitourism.service.POIService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Service
@RequiredArgsConstructor
@Slf4j
public class POIServiceImpl implements POIService {

    private final POIMapper poiMapper;

    @Override
    public Map<String, Object> pageQuery(String cityName, String keyword, Integer page, Integer pageSize) {
        if (page == null || page < 1) page = 1;
        if (pageSize == null || pageSize < 1 || pageSize > 100) pageSize = 10;
        int offset = (page - 1) * pageSize;
        List<POI> list = poiMapper.pageQuery(cityName, keyword, offset, pageSize);
        long total = poiMapper.countQuery(cityName, keyword);
        Map<String, Object> result = new HashMap<>();
        result.put("list", list);
        result.put("total", total);
        result.put("page", page);
        result.put("page_size", pageSize);
        return result;
    }

    @Override
    public POI add(POI poi) {
        if (poi.getPoiName() == null || poi.getPoiName().trim().isEmpty()) {
            throw new RuntimeException("2001: 景点名称不能为空");
        }
        if (poi.getCityName() == null || poi.getCityName().trim().isEmpty()) {
            throw new RuntimeException("2002: 城市名称不能为空");
        }
        poiMapper.insert(poi);
        log.info("新增景点: {} ({})", poi.getPoiName(), poi.getCityName());
        return poi;
    }

    @Override
    public POI update(POI poi) {
        if (poi.getId() == null) {
            throw new RuntimeException("2003: 景点ID不能为空");
        }
        int rows = poiMapper.update(poi);
        if (rows <= 0) {
            throw new RuntimeException("2004: 景点不存在或更新失败");
        }
        log.info("更新景点: id={}", poi.getId());
        return poi;
    }

    @Override
    public void delete(Long id) {
        int rows = poiMapper.deleteById(id);
        if (rows <= 0) {
            throw new RuntimeException("2005: 景点不存在或删除失败");
        }
        log.info("删除景点: id={}", id);
    }

    @Override
    public List<String> listCities() {
        return poiMapper.listCities();
    }
}
