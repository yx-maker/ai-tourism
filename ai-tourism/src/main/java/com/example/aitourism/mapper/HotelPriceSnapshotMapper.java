package com.example.aitourism.mapper;

import com.example.aitourism.entity.HotelPriceSnapshot;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;

@Mapper
public interface HotelPriceSnapshotMapper {

    @Select("SELECT * FROM t_hotel_price_snapshot WHERE city_name = #{cityName} ORDER BY tier")
    List<HotelPriceSnapshot> findByCity(@Param("cityName") String cityName);

    @Select("SELECT * FROM t_hotel_price_snapshot WHERE city_name = #{cityName} AND tier = #{tier} LIMIT 1")
    HotelPriceSnapshot findByCityAndTier(@Param("cityName") String cityName, @Param("tier") String tier);

    @Select("SELECT DISTINCT city_name FROM t_hotel_price_snapshot ORDER BY city_name")
    List<String> listCities();
}
