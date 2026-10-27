package com.example.aitourism.service;

import com.example.aitourism.entity.Favorite;

import java.util.List;

public interface FavoriteService {
    Favorite add(String userId, Long poiId);
    List<Favorite> list(String userId);
    void remove(String userId, Long poiId);
    boolean isFavorite(String userId, Long poiId);
}
