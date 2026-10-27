package com.example.aitourism.service;

import com.example.aitourism.entity.POI;

import java.util.List;
import java.util.Map;

public interface POIService {
    Map<String, Object> pageQuery(String cityName, String keyword, Integer page, Integer pageSize);
    POI add(POI poi);
    POI update(POI poi);
    void delete(Long id);
    List<String> listCities();
}
