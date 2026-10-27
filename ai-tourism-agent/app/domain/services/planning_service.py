"""路线规划服务"""
import os
import re
from typing import Dict, Any, List, Optional, Set, Tuple, TYPE_CHECKING
from loguru import logger
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from app.infrastructure.llm.factory import LLMFactory
from app.config import settings
from app.domain.services.price_provider import get_price_provider

# 国内主要旅游城市词表：用于行程产出后的「串城市」后校验
KNOWN_CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "长沙", "西安", "重庆",
    "厦门", "三亚", "桂林", "丽江", "济南", "福州", "南京", "苏州", "天津", "青岛",
    "大连", "哈尔滨", "昆明", "大理", "贵阳", "兰州", "西宁", "银川", "乌鲁木齐",
    "拉萨", "呼和浩特", "太原", "石家庄", "郑州", "合肥", "南昌", "南宁", "海口",
    "无锡", "宁波", "温州", "珠海", "东莞", "佛山", "泉州", "漳州", "烟台", "威海",
    "洛阳", "开封", "泰安", "黄山", "张家界", "湘西", "凤凰", "丽江古城", "台北",
    "香港", "澳门", "南投", "绍兴", "扬州", "镇江", "常州", "徐州", "嘉兴", "湖州",
]

if TYPE_CHECKING:
    from app.graph.state import AgentState


class PlanningService:
    """路线规划服务类"""

    def __init__(self):
        """初始化路线规划服务"""
        file_path = os.path.abspath(__file__)
        app_dir = os.path.dirname(os.path.dirname(os.path.dirname(file_path)))
        prompt_dir = os.path.join(app_dir, "prompt")
        # 路线规划服务，用于生成旅游路线规划
        self.system_prompt_path = os.path.join(prompt_dir, "route-planning-system-prompt.txt")
        self.user_prompt_path = os.path.join(prompt_dir, "route-planning-user-prompt.txt")

    def _build_budget_block(self, budget_amount, day_count,
                            origin_city: Optional[str] = None,
                            dest_city: Optional[str] = None) -> str:
        """构建「预算硬约束」提示块（预算反推规划的 Prompt 侧实现）。

        委托 PriceProvider 完成：真实票价（火车票 API）→ 快照（酒店/景点库）→
        系数估算的三级取价 + 档次阶梯判定 + 不可行时的最低预算与降级方案。
        PriceProvider 内部任何取价失败都会自动降级，不会阻断规划。

        用户未给出预算时返回空串（模板占位符留空，不产生任何约束）。

        Args:
            budget_amount: 用户给定总预算（元），可为 None
            day_count: 行程天数
            origin_city: 出发城市（用于查询真实火车票价）
            dest_city: 目的地城市（用于查询酒店快照与景点库门票）

        Returns:
            预算约束提示块文本；无预算时为 ""
        """
        try:
            return get_price_provider().build_budget_block(
                budget_amount, day_count, origin_city, dest_city)
        except Exception as e:
            # 价格层异常不能阻断规划：回退到无约束（由 Java 端封套引擎做事后核验）
            logger.error(f"[PLANNING] PriceProvider 预算块构建失败，跳过预算约束: {e}", exc_info=True)
            return ""

    def _build_reference_block(self, origin_city: Optional[str] = None,
                               dest_city: Optional[str] = None) -> str:
        """无预算时的真实价格参考块（至少取到一条真实数据才注入）"""
        try:
            return get_price_provider().build_reference_block(origin_city, dest_city)
        except Exception as e:
            logger.debug(f"[PLANNING] 价格参考块构建失败（忽略）: {e}")
            return ""

    def _build_data_gap_block(self, city_name: Optional[str],
                              poi_info: Optional[str],
                              rag_context: Optional[str],
                              origin_city: Optional[str] = None) -> str:
        """构建「本地数据缺失」提示块。

        景点库 / RAG 都没有目标城市数据时，模型失去事实支撑，极易凭常识
        把其他城市的著名景点张冠李戴（实测：福州行程里冒出「杭州西湖」）。
        这里显式告知模型「无数据可用」并禁止编造，从源头掐掉幻觉。
        """
        city = (city_name or "").strip()
        poi_empty = not poi_info or "暂无" in poi_info or not poi_info.strip()
        rag_empty = not rag_context or not rag_context.strip()

        if not poi_empty and not rag_empty:
            return ""

        missing = []
        if poi_empty:
            missing.append("景点库（t_poi）中**没有**该城市的任何景点记录")
        if rag_empty:
            missing.append("游记知识库中**没有**该城市的任何检索结果")

        allowed = ""
        if origin_city and origin_city.strip():
            allowed = f"（出发城市 {origin_city.strip()} 可正常出现在交通安排中）"

        return (
            "## ⚠️ 本地数据缺失提示（务必遵守）\n"
            f"- 目标城市：**{city}**。系统检索结果显示：{'；'.join(missing)}。\n"
            "- 因此你**没有任何该城市的本地事实数据**作为依据，此时编造景点与价格的风险极高。\n"
            "- 强制要求：\n"
            "  1) 行程中**只能出现属于 "
            f"{city} 的景点{allowed}，严禁写入任何其他城市的景点（例如目的地非杭州时不得出现「西湖」）。\n"
            "  2) 若你无法确认某景点确实位于"
            f"{city}，就不要写它——宁可少写，不可错写。\n"
            "  3) 必须在攻略开头明确声明：「当前景点库未收录该城市数据，以下为通用建议，"
            "开放时间与票价请出行前核实」。\n"
            "  4) 门票价格一律写\"系统估算\"并给区间，**禁止编造精确票价**。\n"
        )

    @staticmethod
    def _stream_once(llm, messages) -> str:
        """执行一次流式生成，返回完整文本（失败时尽量返回已收集的部分内容）。"""
        parts: List[str] = []
        chunk_count = 0
        last_finish_reason = None
        try:
            for chunk in llm.stream(messages):
                if hasattr(chunk, 'response_metadata'):
                    metadata = chunk.response_metadata
                    if metadata and 'finish_reason' in metadata:
                        last_finish_reason = metadata['finish_reason']
                        if last_finish_reason == 'length':
                            logger.warning(
                                "[PLANNING] ⚠️ 检测到finish_reason='length'，输出因token限制被截断！")
                        elif last_finish_reason:
                            logger.info(f"[PLANNING] finish_reason: {last_finish_reason}")

                if hasattr(chunk, 'content') and chunk.content:
                    parts.append(chunk.content)
                    chunk_count += 1
        except Exception as stream_error:
            logger.error(f"[PLANNING] LLM流式调用异常: {stream_error}", exc_info=True)
            if not parts:
                raise

        text = "".join(parts)
        logger.info(
            f"[PLANNING] LLM流式调用完成 - chunks: {chunk_count}, "
            f"长度: {len(text)}, finish_reason: {last_finish_reason}")
        return text

    @staticmethod
    def _detect_foreign_cities(text: str, city_name: Optional[str],
                               origin_city: Optional[str] = None) -> List[str]:
        """扫描生成的攻略，找出「不应出现」的其他城市名（串城市检测）。"""
        if not text:
            return []
        target = (city_name or "").strip()
        allowed: Set[str] = {target} if target else set()
        if origin_city and origin_city.strip():
            allowed.add(origin_city.strip())

        hits: List[str] = []
        for c in KNOWN_CITIES:
            if c in allowed:
                continue
            # 只统计「有实质提及」的城市（≥2 次，避免路过/对比性提及造成误报）
            if text.count(c) >= 2:
                hits.append(c)
        return hits

    def _load_system_prompt(self) -> str:
        """加载系统提示词"""
        try:
            with open(self.system_prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"系统提示词文件不存在: {self.system_prompt_path}")
    
    def _load_user_prompt_template(self) -> str:
        """加载用户提示词模板"""
        try:
            with open(self.user_prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"用户提示词文件不存在: {self.user_prompt_path}")
        
    def plan_route(self, state: "AgentState") -> Dict[str, Any]:
        """
        生成旅游路线规划
        
        Args:
            state: Agent 状态对象
            
        Returns:
            包含路线规划的字典，如果失败则包含 error 字段
        """
        try:
            # 从 state 中提取信息
            weather_info = state.get("weather_data")
            poi_info = state.get("poi_data")
            rag_context = state.get("rag_context")
            city_name = state.get("city_name")
            day_count = state.get("day_count")
            customization_requirements = state.get("customization_requirements")
            budget_amount = state.get("budget_amount")
            origin_city = state.get("origin_city")
            if customization_requirements:
                user_message = f"用户将在 {city_name} 旅游 {day_count} 天；用户定制化需求：{customization_requirements}"
            else:
                user_message = f"用户将在 {city_name} 旅游 {day_count} 天"
            if origin_city:
                user_message += f"；出发城市：{origin_city}"
            if budget_amount:
                user_message += f"；总预算：{float(budget_amount):.0f} 元"

            # 预算硬约束提示块（无预算时为空串，不影响原有行为）
            budget_block = self._build_budget_block(budget_amount, day_count, origin_city, city_name)
            # 无预算时注入真实价格参考（至少取到一条真实数据才非空），让费用表贴近真实行情
            price_block = "" if budget_block else self._build_reference_block(origin_city, city_name)
            
            # 加载提示词
            system_prompt = self._load_system_prompt()
            user_prompt_template = self._load_user_prompt_template()
            
            # 使用 LLM 工厂创建流式 LLM 实例
            llm = LLMFactory.create_streaming_llm(
                temperature=0.7,
                max_tokens=settings.openai_max_output_tokens
            )
            
            # 格式化用户提示词
            weather_info_str = weather_info or "暂无天气信息"
            poi_info_str = poi_info or "暂无景点信息"
            rag_info_str = (rag_context or "").strip() or "暂无相关游记检索结果（或未配置向量库）"

            # 本地数据缺失提示（景点库 / RAG 都没有该城市数据时，强制约束模型不得串城市）
            data_gap_block = self._build_data_gap_block(
                city_name, poi_info_str, rag_info_str, origin_city)

            base_user_prompt = user_prompt_template.format(
                weather_info=weather_info_str,
                poi_info=poi_info_str,
                rag_info=rag_info_str,
                user_message=user_message,
                price_block=price_block,
                budget_block=budget_block,
                data_gap_block=data_gap_block,
            )

            # 调用 LLM（流式调用）
            # agent_service.py 中的 astream_events 会实时捕获这个流式调用过程中的每个 chunk
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=base_user_prompt)
            ]

            route_plan = self._stream_once(llm, messages)

            # ---- 串城市后校验：命中则带纠错指令重试一次（仅一次，避免无限放大延迟）----
            foreign = self._detect_foreign_cities(route_plan, city_name, origin_city)
            if foreign:
                logger.warning(
                    f"[PLANNING] ⚠️ 检测到行程中出现非目标城市内容: {foreign}，"
                    f"目标城市={city_name}，触发一次纠错重试"
                )
                fix_hint = (
                    "## 纠错指令（必须执行）\n"
                    f"你刚才的输出中出现了不属于目标城市「{city_name}」的其他城市内容：{'、'.join(foreign)}。\n"
                    f"请重新生成**完整**攻略，并满足：\n"
                    f"1) 全篇不得再出现 {'、'.join(foreign)} 中的任何城市名及其景点；\n"
                    f"2) 所有景点必须真实位于「{city_name}」，无法确认的景点一律不写；\n"
                    "3) 其余要求（天气、每日行程、费用参考表）保持不变。"
                )
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=base_user_prompt),
                    AIMessage(content=route_plan),
                    HumanMessage(content=fix_hint),
                ]
                retried = self._stream_once(llm, messages)
                if retried:
                    still = self._detect_foreign_cities(retried, city_name, origin_city)
                    if still:
                        logger.error(
                            f"[PLANNING] 纠错重试后仍存在串城市: {still}（保留重试结果，不做二次重试）")
                    else:
                        logger.info("[PLANNING] 纠错重试成功：已消除非目标城市内容")
                    route_plan = retried

            logger.info(f"[PLANNING] 路线规划完成，最终内容长度: {len(route_plan)}")
            return {
                "route_plan": route_plan,
                "messages": [AIMessage(content=route_plan)]
            }
        
        except Exception as e:
            logger.error(f"路线规划异常: {e}", exc_info=True)
            return {"error": f"路线规划失败: {str(e)}"}

