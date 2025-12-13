CREATE DATABASE IF NOT EXISTS gaming_marketplace;
USE gaming_marketplace;

CREATE TABLE users (
    user_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    role ENUM('end_user', 'rep', 'admin') NOT NULL DEFAULT 'end_user',
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci;


CREATE TABLE items (
    item_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    seller_id INT UNSIGNED NOT NULL,

    -- Shared fields
    title VARCHAR(150) NOT NULL,
    description TEXT,
    category ENUM('console', 'game', 'accessory') NOT NULL,
    brand VARCHAR(100),
    platform VARCHAR(50),
    item_condition ENUM('new', 'like_new', 'good', 'fair', 'poor') NOT NULL,
    color VARCHAR(50),
    base_price DECIMAL(10,2) NOT NULL,

    -- Console-specific fields
    storage_capacity VARCHAR(50),     
    console_model VARCHAR(100),       

    -- Game-specific fields
    genre VARCHAR(50),                
    age_rating VARCHAR(10),          
    edition VARCHAR(50),              

    -- Accessory-specific fields
    accessory_type VARCHAR(50),       
    wireless TINYINT(1),              

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,


    CONSTRAINT fk_items_seller
        FOREIGN KEY (seller_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;



CREATE TABLE auctions (
    auction_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    item_id   INT UNSIGNED NOT NULL,
    seller_id INT UNSIGNED NOT NULL,
    winner_id INT UNSIGNED NULL,

    start_time DATETIME NOT NULL,
    end_time   DATETIME NOT NULL,

    -- Pricing
    starting_price   DECIMAL(10,2) NOT NULL,
    current_price    DECIMAL(10,2) NOT NULL,
    bid_increment    DECIMAL(10,2) NOT NULL,
    secret_min_price DECIMAL(10,2) NOT NULL, -- Hidden from consumer
    buy_now_price    DECIMAL(10,2) DEFAULT NULL,  

    -- Status + final sale info
    status ENUM('scheduled', 'running', 'closed', 'cancelled') NOT NULL,
    final_price DECIMAL(10,2) NULL,
    closed_at   DATETIME NULL,           

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    CONSTRAINT fk_auctions_item
        FOREIGN KEY (item_id) REFERENCES items(item_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_auctions_seller
        FOREIGN KEY (seller_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_auctions_winner
        FOREIGN KEY (winner_id) REFERENCES users(user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

CREATE TABLE bids (
    bid_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    -- Relationships
    auction_id INT UNSIGNED NOT NULL,
    bidder_id  INT UNSIGNED NOT NULL,

    -- Bid values
    bid_amount   DECIMAL(10,2) NOT NULL,     
    max_auto_bid DECIMAL(10,2) DEFAULT NULL,  
    is_auto      TINYINT(1) NOT NULL DEFAULT 0, -- 0 = manual, 1 = system auto-bid

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign keys
    CONSTRAINT fk_bids_auction
        FOREIGN KEY (auction_id) REFERENCES auctions(auction_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_bids_bidder
        FOREIGN KEY (bidder_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Helpful indexes
    INDEX idx_bids_auction_created (auction_id, created_at),
    INDEX idx_bids_bidder (bidder_id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

CREATE TABLE alerts (
    alert_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    -- Who owns this alert
    user_id INT UNSIGNED NOT NULL,

    -- Matching criteria (all optional filters)
    category  ENUM('console', 'game', 'accessory') DEFAULT NULL,
    platform  VARCHAR(50)  DEFAULT NULL,   
    brand     VARCHAR(100) DEFAULT NULL,   
    min_price DECIMAL(10,2) DEFAULT NULL,
    max_price DECIMAL(10,2) DEFAULT NULL,
    item_condition ENUM('new', 'like_new', 'good', 'fair', 'poor') DEFAULT NULL,
    keyword   VARCHAR(100) DEFAULT NULL,   


    is_active TINYINT(1) NOT NULL DEFAULT 1, -- status
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Foreign key
    CONSTRAINT fk_alerts_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    INDEX idx_alerts_user (user_id),
    INDEX idx_alerts_basic (category, platform, brand)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;


CREATE TABLE sales (
    sale_id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,

    auction_id INT UNSIGNED NOT NULL UNIQUE,
    item_id    INT UNSIGNED NOT NULL,
    buyer_id   INT UNSIGNED NOT NULL,
    seller_id  INT UNSIGNED NOT NULL,

    sale_price       DECIMAL(10,2) NOT NULL,   

    sold_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_sales_auction
        FOREIGN KEY (auction_id) REFERENCES auctions(auction_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_sales_item
        FOREIGN KEY (item_id) REFERENCES items(item_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_sales_buyer
        FOREIGN KEY (buyer_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_sales_seller
        FOREIGN KEY (seller_id) REFERENCES users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    INDEX idx_sales_seller (seller_id),
    INDEX idx_sales_buyer  (buyer_id)

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

  
