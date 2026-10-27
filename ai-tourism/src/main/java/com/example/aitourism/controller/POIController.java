package com.example.aitourism.controller;

import cn.dev33.satoken.annotation.SaCheckPermission;
import com.example.aitourism.dto.BaseResponse;
import com.example.aitourism.entity.POI;
import com.example.aitourism.service.POIService;
import com.example.aitourism.util.Constants;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * 景点管理模块（开题报告核心模块③）
 * 后台 CRUD：新增/删除/修改景点，景点评分、标签、开放时间、门票价格
 */
@RestController
@RequestMapping("/poi")
@RequiredArgsConstructor
public class POIController {

    private final POIService poiService;

    /** 分页查询景点（支持城市/关键词筛选） */
    @GetMapping("/page")
    public BaseResponse<Map<String, Object>> page(
            @RequestParam(required = false) String cityName,
            @RequestParam(required = false) String keyword,
            @RequestParam(defaultValue = "1") Integer page,
            @RequestParam(defaultValue = "10") Integer pageSize) {
        try {
            return BaseResponse.success(poiService.pageQuery(cityName, keyword, page, pageSize));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 获取全部城市列表 */
    @GetMapping("/cities")
    public BaseResponse<List<String>> cities() {
        try {
            return BaseResponse.success(poiService.listCities());
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 新增景点（需 ROOT 权限） */
    @SaCheckPermission("poi:manage")
    @PostMapping("/add")
    public BaseResponse<POI> add(@RequestBody POI poi) {
        try {
            return BaseResponse.success(poiService.add(poi));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 修改景点（需 ROOT 权限） */
    @SaCheckPermission("poi:manage")
    @PutMapping("/update")
    public BaseResponse<POI> update(@RequestBody POI poi) {
        try {
            return BaseResponse.success(poiService.update(poi));
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    /** 删除景点（需 ROOT 权限） */
    @SaCheckPermission("poi:manage")
    @DeleteMapping("/delete/{id}")
    public BaseResponse<Void> delete(@PathVariable Long id) {
        try {
            poiService.delete(id);
            return BaseResponse.success();
        } catch (RuntimeException e) {
            return BaseResponse.error(parseCode(e), parseMsg(e));
        }
    }

    private int parseCode(RuntimeException e) {
        String msg = e.getMessage();
        if (msg != null && msg.matches("^\\d{4}:.*")) {
            return Integer.parseInt(msg.substring(0, 4));
        }
        return Constants.ERROR_CODE_SERVER_ERROR;
    }

    private String parseMsg(RuntimeException e) {
        String msg = e.getMessage();
        if (msg != null && msg.matches("^\\d{4}:.*")) {
            return msg.substring(6);
        }
        return msg != null ? msg : "服务端错误";
    }
}
