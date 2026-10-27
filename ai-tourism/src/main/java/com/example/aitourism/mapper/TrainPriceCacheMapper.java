package com.example.aitourism.mapper;

import com.example.aitourism.entity.TrainPriceCache;
import org.apache.ibatis.annotations.*;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface TrainPriceCacheMapper {

    /** 查询未过期的缓存（缓存期内直接复用，避免重复消耗 API 次数） */
    @Select("SELECT * FROM t_train_price_cache WHERE origin_city = #{originCity} AND dest_city = #{destCity} " +
            "AND depart_date = #{departDate} AND fetched_at > #{freshAfter}")
    List<TrainPriceCache> findFresh(@Param("originCity") String originCity,
                                    @Param("destCity") String destCity,
                                    @Param("departDate") String departDate,
                                    @Param("freshAfter") LocalDateTime freshAfter);

    /** 写入/更新缓存（同一路线+日期+席别唯一） */
    @Insert("INSERT INTO t_train_price_cache(origin_city, dest_city, depart_date, seat_type, price, provider, fetched_at) " +
            "VALUES(#{originCity}, #{destCity}, #{departDate}, #{seatType}, #{price}, #{provider}, NOW()) " +
            "ON DUPLICATE KEY UPDATE price = VALUES(price), provider = VALUES(provider), fetched_at = NOW()")
    int upsert(TrainPriceCache cache);

    /** 清理过期缓存（可由定时任务调用） */
    @Delete("DELETE FROM t_train_price_cache WHERE fetched_at < DATE_SUB(NOW(), INTERVAL 7 DAY)")
    int cleanExpired();
}
