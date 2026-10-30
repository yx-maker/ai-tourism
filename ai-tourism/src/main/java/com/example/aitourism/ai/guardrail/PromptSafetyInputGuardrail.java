package com.example.aitourism.ai.guardrail;

import dev.langchain4j.data.message.UserMessage;
import dev.langchain4j.guardrail.InputGuardrail;
import dev.langchain4j.guardrail.InputGuardrailResult;
import lombok.extern.slf4j.Slf4j;

import java.util.Arrays;
import java.util.List;
import java.util.regex.Pattern;

/**
 * Prompt 安全审查护轨，用于检测用户输入中的敏感词和提示注入攻击。
 */
@Slf4j
public class PromptSafetyInputGuardrail implements InputGuardrail {

    /**
     * 系统自动注入的规划上下文分隔符。
     *
     * <p>后端会把「真实票价 / 预算约束 / 交通时长 / 用户偏好」等参考数据拼在用户原始提问之后
     * 一起发给模型。这些内容是服务端生成的常量模板，并非用户可控输入，因此不能参与
     * 「用户输入」的长度上限与敏感词/注入检测——否则用户只要多打几个字就会被误判为
     * 「输入内容过长」。护栏在校验时以该分隔符为界，只取前面的部分作为真正的用户输入。
     */
    public static final String CONTEXT_PREFIX = "\n\n[SYSTEM_CONTEXT_BEGIN]\n";

    // 敏感词列表，包含不允许出现在用户输入中的词语或短语。
    private static final List<String> SENSITIVE_WORDS = Arrays.asList(
            "忽略之前的指令", "ignore previous instructions", "ignore above",
            "破解", "hack", "绕过", "bypass", "越狱", "jailbreak"
    );

    // 注入攻击模式，用于检测提示注入攻击的正则表达式模式列表。
    private static final List<Pattern> PROMPT_INJECTION_REGEX_LIST = Arrays.asList(
            Pattern.compile("(?i)ignore\\s+(?:previous|above|all)\\s+(?:instructions?|commands?|prompts?)"), // 忽略之前的系统指令
            Pattern.compile("(?i)(?:forget|disregard)\\s+(?:everything|all)\\s+(?:above|before)"),  // 忘记在之前的对话历史或系统提示
            Pattern.compile("(?i)(?:pretend|act|behave)\\s+(?:as|like)\\s+(?:if|you\\s+are)"),  // 让AI模拟或扮演其他角色
            Pattern.compile("(?i)system\\s*:\\s*you\\s+are"),   // 伪装成系统提示词
            Pattern.compile("(?i)new\\s+(?:instructions?|commands?|prompts?)\\s*:")   // 试图提供新的失灵覆盖原有的系统指令
    );

    /**
     * 校验用户输入的安全性。
     * @param userMessage 用户消息对象
     * @return InputGuardrailResult 校验结果
     */
    @Override
    public InputGuardrailResult validate(UserMessage userMessage) {
        String raw = userMessage.singleText();
        // 只校验用户原始输入：分隔符之后是服务端注入的参考数据，不由用户控制
        int ctxIdx = raw == null ? -1 : raw.indexOf(CONTEXT_PREFIX);
        String userInput = ctxIdx >= 0 ? raw.substring(0, ctxIdx) : (raw == null ? "" : raw);
        String trimmedInput = userInput.trim();
        // 检查输入长度
        if (trimmedInput.length() > 1000) {
            return fatal("输入内容过长，不要超过 1000 字");
        }
        // 检查输入是否为空
        if (trimmedInput.isEmpty()) {
            return fatal("输入内容不能为空");
        }
        // 转小写用于后续检测
        String inputLower = trimmedInput.toLowerCase();
        // 敏感词检测
        for (String sensitiveWord : SENSITIVE_WORDS) {
            if (inputLower.contains(sensitiveWord.toLowerCase())) {
                System.out.println("输入包含不当内容，请修改后重试");
                return fatal("输入包含不当内容，请修改后重试");
            }
        }
        // 提示注入正则检测
        for (Pattern pattern : PROMPT_INJECTION_REGEX_LIST) {
            if (pattern.matcher(trimmedInput).find()) {
                return fatal("检测到恶意输入，请求被拒绝");
            }
        }
        log.info("没有不当内容，校验通过");
        // 校验通过
        return success();
    }
} 