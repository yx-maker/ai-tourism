package com.example.aitourism.service;

import com.example.aitourism.entity.UserPreference;

public interface UserPreferenceService {
    UserPreference get(String userId);
    UserPreference save(String userId, UserPreference pref);
}
