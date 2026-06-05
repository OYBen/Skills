package com.example;

import org.apache.ibatis.annotations.Select;

public interface UserMapper {
    @Select("SELECT status FROM t_user WHERE third_user_id = #{ownerId}")
    String selectOwnerStatus(String ownerId);
}
