package com.example.aitourism.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.info.License;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Knife4j / OpenAPI 接口文档配置
 * 访问地址: http://localhost:8290/doc.html
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("基于大语言模型的智能旅游路线规划系统 API")
                        .description("毕业论文系统：用户管理 / AI路线规划 / 景点管理 / 地图可视化 / 预算分析 / 收藏 / 用户偏好")
                        .version("1.0.0")
                        .contact(new Contact().name("毕业论文"))
                        .license(new License().name("仅供学习研究")));
    }
}
