package com.example.aitourism.service.impl;

import com.example.aitourism.entity.Favorite;
import com.example.aitourism.entity.POI;
import com.example.aitourism.mapper.FavoriteMapper;
import com.example.aitourism.mapper.POIMapper;
import com.example.aitourism.service.FavoriteService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
@RequiredArgsConstructor
@Slf4j
public class FavoriteServiceImpl implements FavoriteService {

    private final FavoriteMapper favoriteMapper;
    private final POIMapper poiMapper;

    @Override
    public Favorite add(String userId, Long poiId) {
        POI poi = poiMapper.findById(poiId);
        if (poi == null) {
            throw new RuntimeException("2001: 景点不存在");
        }
        Favorite existing = favoriteMapper.findByUserAndPoi(userId, poiId);
        if (existing != null) {
            return existing;
        }
        Favorite fav = new Favorite();
        fav.setUserId(userId);
        fav.setPoiId(poiId);
        fav.setPoiName(poi.getPoiName());
        fav.setCityName(poi.getCityName());
        favoriteMapper.insert(fav);
        log.info("用户 {} 收藏景点 {}", userId, poiId);
        return fav;
    }

    @Override
    public List<Favorite> list(String userId) {
        return favoriteMapper.findByUserId(userId);
    }

    @Override
    public void remove(String userId, Long poiId) {
        favoriteMapper.deleteByUserAndPoi(userId, poiId);
    }

    @Override
    public boolean isFavorite(String userId, Long poiId) {
        return favoriteMapper.findByUserAndPoi(userId, poiId) != null;
    }
}
