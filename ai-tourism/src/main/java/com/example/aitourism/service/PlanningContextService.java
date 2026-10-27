package com.example.aitourism.service;

/**
 * 规划上下文服务——把「真实价格」与「用户记忆」注入 AI 规划主链路。
 *
 * <p>论文对应：
 * <ul>
 *   <li>数据真实性分层：{@link #buildContext} 产出「真实价格参考」块
 *       （火车票真实 API / 酒店快照 / 景点库门票），让攻略里的价格可溯源；
 *       拿不到真实价格的项明确标注「系统估算」，绝不把估算伪装成真实价格</li>
 *   <li>预算硬约束：复用 {@link BudgetEnvelopeService} 的档次阶梯引擎，
 *       在生成前就把「该花多少、怎么花」注入 Prompt</li>
 *   <li>跨会话用户记忆：从对话中沉淀偏好画像（{@link #extractAndSavePreferences}），
 *       下次规划时注入（{@link #buildContext} 的偏好块），
 *       对应开题报告数据库设计中的「用户偏好表」</li>
 * </ul>
 */
public interface PlanningContextService {

    /**
     * 构建规划上下文文本（真实价格 + 预算硬约束 + 用户偏好）。
     * 无可用上下文时返回空串（调用方原样发送用户消息）。
     *
     * @param userId      用户ID（用于读取偏好记忆）
     * @param userMessage 用户原始消息
     */
    String buildContext(String userId, String userMessage);

    /**
     * 从一轮对话中沉淀用户偏好画像（LLM 抽取，失败静默，不阻断主流程）。
     * 建议异步调用。
     */
    void extractAndSavePreferences(String userId, String userMessage, String assistantReply);
}
