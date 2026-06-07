DROP DATABASE IF EXISTS library_system;
CREATE DATABASE library_system CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE library_system;
-- 1. 学生表
CREATE TABLE Student (
    sno VARCHAR(20) PRIMARY KEY COMMENT '学号',
    sname VARCHAR(50) NOT NULL COMMENT '姓名',
    spassword VARCHAR(255) NOT NULL COMMENT '密码(MD5)',
    sclass VARCHAR(50) COMMENT '班级',
    sphone VARCHAR(20) COMMENT '电话',
    semail VARCHAR(100) COMMENT '邮箱',
    photo VARCHAR(255) COMMENT '照片路径'
);
-- 2. 管理员表
CREATE TABLE Admin (
    ano VARCHAR(20) PRIMARY KEY COMMENT '工号',
    aname VARCHAR(50) NOT NULL COMMENT '姓名',
    apassword VARCHAR(255) NOT NULL COMMENT '密码(MD5)',
    aphone VARCHAR(20) COMMENT '电话'
);

-- 3. 图书表
CREATE TABLE Book (
    bid VARCHAR(20) PRIMARY KEY COMMENT '图书号',
    bname VARCHAR(100) NOT NULL COMMENT '书名',
    author VARCHAR(50) COMMENT '作者',
    publisher VARCHAR(50) COMMENT '出版社',
    price DECIMAL(10,2) COMMENT '价格',
    total_count INT DEFAULT 1 COMMENT '总本数',
    available_count INT DEFAULT 1 COMMENT '剩余可借本数',
    borrow_Times INT DEFAULT 0 COMMENT '总借阅次数',
    reserve_Times INT DEFAULT 0 COMMENT '当前预约人数',
    cover VARCHAR(255) COMMENT '封面路径'
);
-- 4. 借阅表
CREATE TABLE Borrow (
    borrow_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '借阅编号',
    sno VARCHAR(20) NOT NULL COMMENT '学号',
    bid VARCHAR(20) NOT NULL COMMENT '图书号',
    borrow_date DATE NOT NULL COMMENT '借书日期',
    return_date DATE COMMENT '实际还书日期',
    FOREIGN KEY (sno) REFERENCES Student(sno) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (bid) REFERENCES Book(bid) ON UPDATE CASCADE ON DELETE CASCADE,
    INDEX idx_borrow_active (sno, return_date)
);
-- 5. 预约表
CREATE TABLE Reserve (
    reserve_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '预约编号',
    sno VARCHAR(20) NOT NULL COMMENT '学号',
    bid VARCHAR(20) NOT NULL COMMENT '图书号',
    reserve_date DATE NOT NULL COMMENT '预约日期',
    take_date DATE COMMENT '取书日期',
    FOREIGN KEY (sno) REFERENCES Student(sno) ON UPDATE CASCADE ON DELETE CASCADE,
    FOREIGN KEY (bid) REFERENCES Book(bid) ON UPDATE CASCADE ON DELETE CASCADE,
    INDEX idx_reserve_active (bid, sno, reserve_date, take_date)
);
-- 6. 逾期表（只记录是否处理，天数和金额动态计算）
CREATE TABLE Overdue (
    overdue_id INT PRIMARY KEY AUTO_INCREMENT COMMENT '逾期编号',
    borrow_id INT NOT NULL COMMENT '借阅编号',
    is_paid BOOLEAN DEFAULT FALSE COMMENT '是否已处理',
    paid_date DATE COMMENT '处理日期',
    FOREIGN KEY (borrow_id) REFERENCES Borrow(borrow_id) ON UPDATE CASCADE ON DELETE CASCADE
);
-- 7. 函数 - 获取当前借阅数量
DELIMITER $$
DROP FUNCTION IF EXISTS GetCurrentBorrowCount$$
CREATE FUNCTION GetCurrentBorrowCount(p_sno VARCHAR(20))
RETURNS INT
DETERMINISTIC
BEGIN
    DECLARE cnt INT;
    SELECT COUNT(*) INTO cnt FROM Borrow 
    WHERE sno = p_sno AND return_date IS NULL;
    RETURN cnt;
END$$
DELIMITER ;

-- 8. 存储过程 - 借书
DROP PROCEDURE IF EXISTS BorrowBook;
DELIMITER $$

CREATE PROCEDURE BorrowBook(
    IN p_sno VARCHAR(20),
    IN p_bid VARCHAR(20),
    OUT p_msg VARCHAR(100),
    OUT p_code INT
)
BEGIN
    DECLARE v_available INT;
    DECLARE v_borrow_count INT;
    DECLARE v_reserve_exists INT;
    DECLARE v_today_borrow INT;
    DECLARE v_other_reserve INT;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_msg = '系统错误，借书失败';
        SET p_code = 99;
    END;
    
    START TRANSACTION;
    
    -- 检查当天是否重复借阅
    SELECT COUNT(*) INTO v_today_borrow
    FROM Borrow 
    WHERE sno = p_sno AND bid = p_bid AND borrow_date = CURDATE();
    
    IF v_today_borrow > 0 THEN
        SET p_msg = CONCAT(p_bid, '：借书失败：同一天不允许重复借阅');
        SET p_code = 4;
        ROLLBACK;
    ELSE
        -- 检查借阅数量
        SET v_borrow_count = GetCurrentBorrowCount(p_sno);
        IF v_borrow_count >= 3 THEN
            SET p_msg = CONCAT(p_bid, '：借书失败：已达借阅上限3本');
            SET p_code = 1;
            ROLLBACK;
        ELSE
            -- 检查库存
            SELECT available_count INTO v_available FROM Book WHERE bid = p_bid;
            
            IF v_available IS NULL THEN
                SET p_msg = CONCAT(p_bid, '：借书失败：图书不存在');
                SET p_code = 3;
                ROLLBACK;
            ELSEIF v_available <= 0 THEN
                SET p_msg = CONCAT(p_bid, '：借书失败：图书已无库存');
                SET p_code = 2;
                ROLLBACK;
            ELSE
                -- 检查预约
                SELECT COUNT(*) INTO v_reserve_exists 
                FROM Reserve 
                WHERE bid = p_bid AND sno = p_sno 
                  AND take_date IS NULL 
                  AND DATE_ADD(reserve_date, INTERVAL 7 DAY) >= CURDATE();
                
                SELECT COUNT(*) INTO v_other_reserve 
                FROM Reserve 
                WHERE bid = p_bid AND sno != p_sno 
                  AND take_date IS NULL 
                  AND DATE_ADD(reserve_date, INTERVAL 7 DAY) >= CURDATE();
                
                IF v_other_reserve > 0 AND v_reserve_exists = 0 THEN
                    SET p_msg = CONCAT(p_bid, '：借书失败：图书已被预约，只有预约者能借');
                    SET p_code = 5;
                    ROLLBACK;
                ELSE
                    -- 插入借阅记录
                    INSERT INTO Borrow(sno, bid, borrow_date, return_date)
                    VALUES(p_sno, p_bid, CURDATE(), NULL);
                    
                    -- 如果有预约，删除预约记录
                    IF v_reserve_exists > 0 THEN
                        DELETE FROM Reserve 
                        WHERE bid = p_bid AND sno = p_sno 
                          AND take_date IS NULL 
                          AND DATE_ADD(reserve_date, INTERVAL 7 DAY) >= CURDATE();
                    END IF;
                    
                    SET p_msg = CONCAT(p_bid, '：借书成功');
                    SET p_code = 0;
                    COMMIT;
                END IF;
            END IF;
        END IF;
    END IF;
END$$

DELIMITER ;
-- 9. 存储过程 - 还书（动态计算应还日期）
DROP PROCEDURE IF EXISTS ReturnBook;
DELIMITER $$

CREATE PROCEDURE ReturnBook(
    IN p_sno VARCHAR(20),
    IN p_bid VARCHAR(20),
    OUT p_msg VARCHAR(100),
    OUT p_code INT
)
BEGIN
    DECLARE v_borrow_id INT;
    DECLARE v_borrow_date DATE;
    DECLARE v_due_date DATE;
    DECLARE v_overdue INT;
    
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_msg = '系统错误，还书失败';
        SET p_code = 99;
    END;
    
    START TRANSACTION;
    
    SELECT borrow_id, borrow_date INTO v_borrow_id, v_borrow_date
    FROM Borrow 
    WHERE sno = p_sno AND bid = p_bid AND return_date IS NULL
    LIMIT 1;
    
    IF v_borrow_id IS NULL THEN
        SET p_msg = CONCAT(p_bid, '：还书失败：未找到借阅记录');
        SET p_code = 1;
        ROLLBACK;
    ELSE
        -- 计算应还日期 = 借阅日期 + 30天
        SET v_due_date = DATE_ADD(v_borrow_date, INTERVAL 30 DAY);
        
        -- 更新还书日期
        UPDATE Borrow 
        SET return_date = CURDATE()
        WHERE borrow_id = v_borrow_id;
        
        -- 计算逾期天数
        SET v_overdue = DATEDIFF(CURDATE(), v_due_date);
        
        -- 如果逾期，记录逾期记录
        IF v_overdue > 0 THEN
            INSERT INTO Overdue(borrow_id, is_paid, paid_date)
            VALUES(v_borrow_id, FALSE, NULL);
            SET p_msg = CONCAT(p_bid, '：还书成功，逾期', v_overdue, '天');
        ELSE
            SET p_msg = CONCAT(p_bid, '：还书成功');
        END IF;
        
        SET p_code = 0;
        COMMIT;
    END IF;
END$$

DELIMITER ;
-- 10. 存储过程 - 删除逾期记录
DROP PROCEDURE IF EXISTS DeleteOverdue;
DELIMITER $$

CREATE PROCEDURE DeleteOverdue(
    IN p_overdue_id INT,
    OUT p_msg VARCHAR(100),
    OUT p_code INT
)
BEGIN
    DECLARE EXIT HANDLER FOR SQLEXCEPTION
    BEGIN
        ROLLBACK;
        SET p_msg = '系统错误，删除失败';
        SET p_code = 99;
    END;
    
    START TRANSACTION;
    
    IF NOT EXISTS (SELECT 1 FROM Overdue WHERE overdue_id = p_overdue_id) THEN
        SET p_msg = '删除失败：逾期记录不存在';
        SET p_code = 1;
        ROLLBACK;
    ELSE
        DELETE FROM Overdue WHERE overdue_id = p_overdue_id;
        SET p_msg = '删除成功';
        SET p_code = 0;
        COMMIT;
    END IF;
END$$

DELIMITER ;
-- 11. 触发器 - 预约插入
DROP TRIGGER IF EXISTS reserve_insert_trigger;
DELIMITER $$

CREATE TRIGGER reserve_insert_trigger
AFTER INSERT ON Reserve
FOR EACH ROW
BEGIN
    UPDATE Book SET reserve_Times = reserve_Times + 1 WHERE bid = NEW.bid;
END$$

DELIMITER ;
-- 12. 触发器 - 预约删除（减少预约人数）
DROP TRIGGER IF EXISTS reserve_delete_trigger;
DELIMITER $$

CREATE TRIGGER reserve_delete_trigger
AFTER DELETE ON Reserve
FOR EACH ROW
BEGIN
    UPDATE Book SET reserve_Times = reserve_Times - 1 
    WHERE bid = OLD.bid AND reserve_Times > 0;
END$$

DELIMITER ;
-- 13. 触发器 - 借阅插入（减少库存，增加借阅次数）
DROP TRIGGER IF EXISTS borrow_insert_trigger;
DELIMITER $$

CREATE TRIGGER borrow_insert_trigger
AFTER INSERT ON Borrow
FOR EACH ROW
BEGIN
    IF NEW.return_date IS NULL THEN
        UPDATE Book SET 
            available_count = available_count - 1,
            borrow_Times = borrow_Times + 1
        WHERE bid = NEW.bid;
    END IF;
END$$

DELIMITER ;
-- 14. 触发器 - 借阅更新（还书时增加库存）
DROP TRIGGER IF EXISTS borrow_update_trigger;
DELIMITER $$

CREATE TRIGGER borrow_update_trigger
AFTER UPDATE ON Borrow
FOR EACH ROW
BEGIN
    IF OLD.return_date IS NULL AND NEW.return_date IS NOT NULL THEN
        UPDATE Book SET available_count = available_count + 1
        WHERE bid = NEW.bid;
    END IF;
END$$

DELIMITER ;

-- 15.创建事件，每天凌晨2点自动执行删除过期预约
DROP EVENT IF EXISTS event_delete_expired_reserves;
DELIMITER $$

CREATE EVENT event_delete_expired_reserves
ON SCHEDULE EVERY 1 DAY
STARTS CONCAT(CURDATE(), ' 19:20:00')
DO
BEGIN
    DELETE FROM Reserve 
    WHERE take_date IS NULL 
      AND DATE_ADD(reserve_date, INTERVAL 7 DAY) < CURDATE();
END$$

DELIMITER ;

-- 开启事件调度器（如果尚未开启）
SET GLOBAL event_scheduler = ON;

DELIMITER ;
-- 16. 插入测试数据

-- 学生数据
INSERT INTO Student (sno, sname, spassword, sclass, sphone, semail, photo) VALUES
('PB001', '小明', MD5('001'), '计算机1班', '13000001234', 'ming@mail.ustc.edu.cn', 'static/photo.png'),
('PB002', '小阳', MD5('002'), '计算机1班', '13000002345', 'yang@mail.ustc.edu.cn', NULL),
('PB003', '小美', MD5('003'), '软件工程1班', '13000003456', 'mei@mail.ustc.edu.cn', NULL);

-- 管理员数据
INSERT INTO Admin (ano, aname, apassword, aphone) VALUES
('A001', 'admin', MD5('123456'), '12306');

-- 图书数据
INSERT INTO Book (bid, bname, author, publisher, price, total_count, available_count, borrow_Times, reserve_Times, cover) VALUES
('B001', '数据库系统概论', '王珊', '高等教育出版社', 68.00, 5, 5, 0, 0, 'static/数据库.png'),
('B002', '计算机网络', '谢希仁', '电子工业出版社', 59.00, 3, 3, 0, 0,'static/计网.png'),
('B003', '操作系统', '汤小丹', '西安电子科大', 72.00, 4, 4, 0, 0, 'static/os.png'),
('B004', '软件工程', '张海藩', '清华大学出版社', 55.00, 1, 1, 0, 0,'static/软件工程.png'),
('B005', '数据结构', '严蔚敏', '清华大学出版社', 48.00, 3, 3, 0, 0, 'static/数据结构.png'),
('B006', 'Advanced SQL Programming', 'Silberschatz', NULL, 72.00, 5, 5, 0, 0, NULL);

-- 借阅记录
INSERT INTO Borrow (sno, bid, borrow_date, return_date) VALUES
('PB001', 'B001', '2026-05-01', NULL),
('PB001', 'B002', '2026-05-10', NULL);

-- 预约记录
INSERT INTO Reserve (sno, bid, reserve_date, take_date) VALUES
('PB002', 'B006', '2026-03-31', NULL);

-- 逾期记录1（逾期未还，应还日期=2026-05-01）
INSERT INTO Borrow (sno, bid, borrow_date, return_date) VALUES
('PB002', 'B001', '2026-04-01', NULL);
SET @borrow_id1 = LAST_INSERT_ID();
INSERT INTO Overdue (borrow_id, is_paid, paid_date) VALUES
(@borrow_id1, FALSE, NULL);

-- 逾期记录2（逾期未还，应还日期=2026-05-31）
INSERT INTO Borrow (sno, bid, borrow_date, return_date) VALUES
('PB003', 'B003', '2026-05-01', NULL);
SET @borrow_id2 = LAST_INSERT_ID();
INSERT INTO Overdue (borrow_id, is_paid, paid_date) VALUES
(@borrow_id2, FALSE, NULL);

-- 逾期记录3（已归还并处理，应还日期=2026-06-09，实际还书=2026-06-16）
INSERT INTO Borrow (sno, bid, borrow_date, return_date) VALUES
('PB001', 'B004', '2026-05-10', '2026-06-16');
SET @borrow_id3 = LAST_INSERT_ID();
INSERT INTO Overdue (borrow_id, is_paid, paid_date) VALUES
(@borrow_id3, TRUE, '2026-06-16');
