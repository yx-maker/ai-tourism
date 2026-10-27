package com.example.aitourism.mapper;

import com.example.aitourism.entity.TravelPlan;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface TravelPlanMapper {

    @Insert("INSERT INTO t_travel_plan(plan_id, user_id, session_id, title, dest_city, origin_city, " +
            "days, budget_amount, content, daily_routes, budget_json, status, version) " +
            "VALUES(#{planId}, #{userId}, #{sessionId}, #{title}, #{destCity}, #{originCity}, " +
            "#{days}, #{budgetAmount}, #{content}, #{dailyRoutes}, #{budgetJson}, " +
            "#{status}, #{version})")
    int insert(TravelPlan plan);

    @Select("SELECT * FROM t_travel_plan WHERE plan_id = #{planId}")
    TravelPlan findByPlanId(@Param("planId") String planId);

    /** 归属校验：只允许本人访问自己的计划（对象级授权） */
    @Select("SELECT * FROM t_travel_plan WHERE plan_id = #{planId} AND user_id = #{userId}")
    TravelPlan findByPlanIdAndUser(@Param("planId") String planId, @Param("userId") String userId);

    @Select("SELECT * FROM t_travel_plan WHERE user_id = #{userId} AND status = 'ACTIVE' " +
            "ORDER BY modify_time DESC LIMIT #{offset}, #{limit}")
    List<TravelPlan> pageByUser(@Param("userId") String userId,
                                @Param("offset") Integer offset, @Param("limit") Integer limit);

    @Select("SELECT COUNT(*) FROM t_travel_plan WHERE user_id = #{userId} AND status = 'ACTIVE'")
    long countByUser(@Param("userId") String userId);

    /**
     * 乐观锁更新：version 不匹配时更新 0 行（调用方据此返回 409）。
     * version 由数据库侧 +1，避免并发自增丢失。
     */
    @Update("<script>" +
            "UPDATE t_travel_plan SET " +
            "<if test='title != null'> title = #{title}, </if>" +
            "<if test='destCity != null'> dest_city = #{destCity}, </if>" +
            "<if test='originCity != null'> origin_city = #{originCity}, </if>" +
            "<if test='days != null'> days = #{days}, </if>" +
            "<if test='budgetAmount != null'> budget_amount = #{budgetAmount}, </if>" +
            "<if test='content != null'> content = #{content}, </if>" +
            "<if test='dailyRoutes != null'> daily_routes = #{dailyRoutes}, </if>" +
            "<if test='budgetJson != null'> budget_json = #{budgetJson}, </if>" +
            " version = version + 1 " +
            "WHERE plan_id = #{planId} AND user_id = #{userId} AND version = #{expectedVersion}" +
            "</script>")
    int updateWithVersionCheck(@Param("planId") String planId,
                               @Param("userId") String userId,
                               @Param("expectedVersion") Integer expectedVersion,
                               @Param("title") String title,
                               @Param("destCity") String destCity,
                               @Param("originCity") String originCity,
                               @Param("days") Integer days,
                               @Param("budgetAmount") java.math.BigDecimal budgetAmount,
                               @Param("content") String content,
                               @Param("dailyRoutes") String dailyRoutes,
                               @Param("budgetJson") String budgetJson);

    /** 软删除：归档而非物理删除，保留历史记录 */
    @Update("UPDATE t_travel_plan SET status = 'ARCHIVED' WHERE plan_id = #{planId} AND user_id = #{userId}")
    int archiveByPlanId(@Param("planId") String planId, @Param("userId") String userId);
}
