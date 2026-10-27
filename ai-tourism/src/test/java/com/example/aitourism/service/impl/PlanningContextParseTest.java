package com.example.aitourism.service.impl;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.*;

/**
 * 规划上下文服务：需求解析（城市 / 天数 / 预算）单元测试。
 *
 * <p>这些解析器决定「真实价格参考」与「预算硬约束」能否在正确场景触发，
 * 是注入链路的第一关。
 */
class PlanningContextParseTest {

    @Test
    @DisplayName("目的地城市：「成都玩5天」「去西安旅游」等模式")
    void shouldExtractDestCity() {
        assertEquals("成都", PlanningContextServiceImpl.extractDestCity("从广州出发去成都玩5天，预算3000元"));
        assertEquals("西安", PlanningContextServiceImpl.extractDestCity("想去西安旅游，4天"));
        assertNull(PlanningContextServiceImpl.extractDestCity("今天天气怎么样"));
        // 「从北京出发」中的北京是出发地而非目的地
        assertNull(PlanningContextServiceImpl.extractDestCity("从北京出发"));
    }

    @Test
    @DisplayName("行程天数：支持阿拉伯数字、中文数字、N天N晚")
    void shouldExtractDays() {
        assertEquals(5, PlanningContextServiceImpl.extractDays("去成都玩5天"));
        assertEquals(3, PlanningContextServiceImpl.extractDays("西安三天两晚攻略"));
        assertEquals(4, PlanningContextServiceImpl.extractDays("4日游"));
        assertEquals(0, PlanningContextServiceImpl.extractDays("推荐几个景点"));
    }

    @Test
    @DisplayName("用户预算：阿拉伯数字与中文数字（带千/万）")
    void shouldExtractBudget() {
        assertEquals(new BigDecimal("3000"), PlanningContextServiceImpl.extractBudget("预算3000元"));
        assertEquals(new BigDecimal("5000"), PlanningContextServiceImpl.extractBudget("花费5000块可以去哪"));
        assertEquals(new BigDecimal("3000"), PlanningContextServiceImpl.extractBudget("预算三千元"));
        assertNull(PlanningContextServiceImpl.extractBudget("三天两晚行程"),
                "「三天两晚」不是预算，应返回 null");
    }
}
