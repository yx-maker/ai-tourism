package com.example.aitourism.mapper;

import com.example.aitourism.entity.Budget;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface BudgetMapper {

    @Insert("INSERT INTO t_budget(session_id, user_id, total_budget, transport_cost, accommodation_cost, " +
            "food_cost, ticket_cost, other_cost, days, detail_json, " +
            "user_budget, budget_status, remaining_budget, envelope_json, plan_json) " +
            "VALUES(#{sessionId}, #{userId}, #{totalBudget}, #{transportCost}, #{accommodationCost}, " +
            "#{foodCost}, #{ticketCost}, #{otherCost}, #{days}, #{detailJson}, " +
            "#{userBudget}, #{budgetStatus}, #{remainingBudget}, #{envelopeJson}, #{planJson})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(Budget budget);

    @Update("UPDATE t_budget SET total_budget = #{totalBudget}, transport_cost = #{transportCost}, " +
            "accommodation_cost = #{accommodationCost}, food_cost = #{foodCost}, ticket_cost = #{ticketCost}, " +
            "other_cost = #{otherCost}, days = #{days}, detail_json = #{detailJson}, " +
            "user_budget = #{userBudget}, budget_status = #{budgetStatus}, " +
            "remaining_budget = #{remainingBudget}, envelope_json = #{envelopeJson}, plan_json = #{planJson} " +
            "WHERE session_id = #{sessionId}")
    int updateBySession(Budget budget);

    @Select("SELECT * FROM t_budget WHERE session_id = #{sessionId}")
    Budget findBySessionId(@Param("sessionId") String sessionId);

    @Select("SELECT * FROM t_budget WHERE user_id = #{userId} ORDER BY created_time DESC LIMIT #{limit}")
    List<Budget> findRecentByUserId(@Param("userId") String userId, @Param("limit") Integer limit);
}
