package com.example.aitourism.mapper;

import com.example.aitourism.entity.UserPreference;
import org.apache.ibatis.annotations.*;

@Mapper
public interface UserPreferenceMapper {

    @Select("SELECT * FROM t_user_preference WHERE user_id = #{userId}")
    UserPreference findByUserId(@Param("userId") String userId);

    @Insert("INSERT INTO t_user_preference(user_id, budget_min, budget_max, travel_style, interests, pace, companion) " +
            "VALUES(#{userId}, #{budgetMin}, #{budgetMax}, #{travelStyle}, #{interests}, #{pace}, #{companion})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(UserPreference pref);

    @Update("UPDATE t_user_preference SET budget_min = #{budgetMin}, budget_max = #{budgetMax}, " +
            "travel_style = #{travelStyle}, interests = #{interests}, pace = #{pace}, companion = #{companion} " +
            "WHERE user_id = #{userId}")
    int update(UserPreference pref);
}
