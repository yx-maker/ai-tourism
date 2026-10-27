package com.example.aitourism.mapper;

import com.example.aitourism.entity.POI;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface POIMapper {

    @Select("SELECT * FROM t_poi WHERE city_name = #{cityName} ORDER BY poi_rankInCity ASC LIMIT #{limit}")
    List<POI> findByCityName(@Param("cityName") String cityName, @Param("limit") Integer limit);

    @Select("SELECT * FROM t_poi WHERE id = #{id}")
    POI findById(@Param("id") Long id);

    @Select("SELECT * FROM t_poi WHERE poi_name = #{poiName} AND city_name = #{cityName} LIMIT 1")
    POI findByNameAndCity(@Param("poiName") String poiName, @Param("cityName") String cityName);

    @Select("SELECT * FROM t_poi WHERE poi_name LIKE CONCAT('%', #{poiName}, '%') LIMIT 1")
    POI findByPoiNameFuzzy(@Param("poiName") String poiName);

    /**
     * 带城市限定的模糊匹配：只在指定城市内按景点名模糊查找。
     * 用于路线坐标补全——避免「福州动物园」被匹配成其他城市的同名景点（坐标画到别的城市）。
     */
    @Select("SELECT * FROM t_poi WHERE city_name = #{cityName} " +
            "AND poi_name LIKE CONCAT('%', #{poiName}, '%') LIMIT 1")
    POI findByPoiNameFuzzyInCity(@Param("poiName") String poiName, @Param("cityName") String cityName);

    // 分页查询：支持城市筛选
    @Select("<script>" +
            "SELECT * FROM t_poi " +
            "<where>" +
            "<if test='cityName != null and cityName != \"\"'> AND city_name = #{cityName} </if>" +
            "<if test='keyword != null and keyword != \"\"'> AND poi_name LIKE CONCAT('%', #{keyword}, '%') </if>" +
            "</where>" +
            "ORDER BY poi_rankInChina ASC LIMIT #{offset}, #{limit}" +
            "</script>")
    List<POI> pageQuery(@Param("cityName") String cityName, @Param("keyword") String keyword,
                        @Param("offset") Integer offset, @Param("limit") Integer limit);

    @Select("<script>" +
            "SELECT COUNT(*) FROM t_poi " +
            "<where>" +
            "<if test='cityName != null and cityName != \"\"'> AND city_name = #{cityName} </if>" +
            "<if test='keyword != null and keyword != \"\"'> AND poi_name LIKE CONCAT('%', #{keyword}, '%') </if>" +
            "</where>" +
            "</script>")
    long countQuery(@Param("cityName") String cityName, @Param("keyword") String keyword);

    @Select("SELECT DISTINCT city_name FROM t_poi ORDER BY city_name")
    List<String> listCities();

    /** 某城市有真实票价的景点平均票价（预算引擎门票估算用，拿不到返回 null） */
    @Select("SELECT AVG(ticket_price) FROM t_poi WHERE city_name = #{cityName} AND ticket_price > 0")
    java.math.BigDecimal avgTicketPriceByCity(@Param("cityName") String cityName);

    /** 某城市有真实票价的景点数量 */
    @Select("SELECT COUNT(*) FROM t_poi WHERE city_name = #{cityName} AND ticket_price > 0")
    int countPricedPoiByCity(@Param("cityName") String cityName);

    /** 某城市景点总数（用于折算免费景点占比，避免把免费景点也算成收费） */
    @Select("SELECT COUNT(*) FROM t_poi WHERE city_name = #{cityName}")
    int countPoiByCity(@Param("cityName") String cityName);

    /** 某城市「已采集过票价」的景点数（ticket_collected_at 非空，区分「真免费」与「没数据」） */
    @Select("SELECT COUNT(*) FROM t_poi WHERE city_name = #{cityName} "
            + "AND ticket_collected_at IS NOT NULL")
    int countTicketCollectedByCity(@Param("cityName") String cityName);

    @Insert("INSERT INTO t_poi(poi_name, city_name, poi_description, poi_longitude, poi_latitude, " +
            "poi_rankInCity, poi_rankInChina, ticket_price) " +
            "VALUES(#{poiName}, #{cityName}, #{poiDescription}, #{poiLongitude}, #{poiLatitude}, " +
            "#{poiRankInCity}, #{poiRankInChina}, #{ticketPrice})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(POI poi);

    @Update("UPDATE t_poi SET poi_name = #{poiName}, city_name = #{cityName}, poi_description = #{poiDescription}, " +
            "poi_longitude = #{poiLongitude}, poi_latitude = #{poiLatitude}, " +
            "poi_rankInCity = #{poiRankInCity}, poi_rankInChina = #{poiRankInChina}, ticket_price = #{ticketPrice} " +
            "WHERE id = #{id}")
    int update(POI poi);

    @Delete("DELETE FROM t_poi WHERE id = #{id}")
    int deleteById(@Param("id") Long id);
}
