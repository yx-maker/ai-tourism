package com.example.aitourism.mapper;

import com.example.aitourism.entity.Favorite;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface FavoriteMapper {

    @Insert("INSERT INTO t_favorite(user_id, poi_id, poi_name, city_name) " +
            "VALUES(#{userId}, #{poiId}, #{poiName}, #{cityName})")
    @Options(useGeneratedKeys = true, keyProperty = "id")
    int insert(Favorite favorite);

    @Select("SELECT * FROM t_favorite WHERE user_id = #{userId} AND poi_id = #{poiId} LIMIT 1")
    Favorite findByUserAndPoi(@Param("userId") String userId, @Param("poiId") Long poiId);

    @Select("SELECT * FROM t_favorite WHERE user_id = #{userId} ORDER BY created_time DESC")
    List<Favorite> findByUserId(@Param("userId") String userId);

    @Delete("DELETE FROM t_favorite WHERE user_id = #{userId} AND poi_id = #{poiId}")
    int deleteByUserAndPoi(@Param("userId") String userId, @Param("poiId") Long poiId);

    @Delete("DELETE FROM t_favorite WHERE id = #{id} AND user_id = #{userId}")
    int deleteByIdAndUser(@Param("id") Long id, @Param("userId") String userId);

    @Select("SELECT COUNT(*) FROM t_favorite WHERE user_id = #{userId}")
    long countByUserId(@Param("userId") String userId);
}
