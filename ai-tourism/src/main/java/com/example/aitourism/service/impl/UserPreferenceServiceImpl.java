package com.example.aitourism.service.impl;

import com.example.aitourism.entity.UserPreference;
import com.example.aitourism.mapper.UserPreferenceMapper;
import com.example.aitourism.service.UserPreferenceService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

@Service
@RequiredArgsConstructor
@Slf4j
public class UserPreferenceServiceImpl implements UserPreferenceService {

    private final UserPreferenceMapper prefMapper;

    @Override
    public UserPreference get(String userId) {
        UserPreference pref = prefMapper.findByUserId(userId);
        if (pref == null) {
            pref = new UserPreference();
            pref.setUserId(userId);
        }
        return pref;
    }

    @Override
    public UserPreference save(String userId, UserPreference pref) {
        pref.setUserId(userId);
        UserPreference existing = prefMapper.findByUserId(userId);
        if (existing == null) {
            prefMapper.insert(pref);
        } else {
            prefMapper.update(pref);
        }
        log.info("用户 {} 保存偏好: 预算{}-{} 风格={} 兴趣={} 节奏={} 同行={}",
                userId, pref.getBudgetMin(), pref.getBudgetMax(), pref.getTravelStyle(),
                pref.getInterests(), pref.getPace(), pref.getCompanion());
        return prefMapper.findByUserId(userId);
    }
}
