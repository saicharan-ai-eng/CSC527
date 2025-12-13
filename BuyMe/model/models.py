from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.mysql import INTEGER as MySQL_INTEGER

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    user_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(100))

    role = db.Column(
        db.Enum("end_user", "rep", "admin", name="user_role_enum"),
        nullable=False,
        server_default="end_user",
    )

    is_active = db.Column(db.Boolean, nullable=False, server_default="1")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    items = db.relationship("Item", back_populates="seller", lazy="dynamic")
    bids = db.relationship("Bid", back_populates="bidder", lazy="dynamic")
    alerts = db.relationship("Alert", back_populates="user", lazy="dynamic")

    def __repr__(self):
        return f"<User {self.user_id} {self.username!r}>"


class Item(db.Model):
    __tablename__ = "items"

    item_id = db.Column(db.Integer, primary_key=True)

    seller_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    category = db.Column(
        db.Enum("console", "game", "accessory", name="category_enum"),
        nullable=False,
    )
    brand = db.Column(db.String(100))
    platform = db.Column(db.String(50))
    color = db.Column(db.String(50))
    item_condition = db.Column(
        db.Enum("new", "like_new", "good", "fair", "poor", name="condition_enum"),
        nullable=False,
    )
    base_price = db.Column(db.Numeric(10, 2), nullable=False)

    storage_capacity = db.Column(db.String(50))
    console_model = db.Column(db.String(100))

    genre = db.Column(db.String(50))
    age_rating = db.Column(db.String(10))
    edition = db.Column(db.String(50))

    accessory_type = db.Column(db.String(50))
    wireless = db.Column(db.Boolean)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    seller = db.relationship("User", back_populates="items")
    auctions = db.relationship("Auction", back_populates="item", lazy="dynamic")
    sales = db.relationship("Sale", back_populates="item", lazy="dynamic")

    def __repr__(self):
        return f"<Item {self.item_id} {self.title!r}>"


class Auction(db.Model):
    __tablename__ = "auctions"

    auction_id = db.Column(db.Integer, primary_key=True)

    item_id = db.Column(
        db.Integer,
        db.ForeignKey("items.item_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    seller_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    winner_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)

    starting_price = db.Column(db.Numeric(10, 2), nullable=False)
    current_price = db.Column(db.Numeric(10, 2), nullable=False)
    bid_increment = db.Column(db.Numeric(10, 2), nullable=False)
    secret_min_price = db.Column(db.Numeric(10, 2), nullable=False)
    buy_now_price = db.Column(db.Numeric(10, 2))

    status = db.Column(
        db.Enum(
            "scheduled",
            "running",
            "ended",
            "cancelled",
            name="auction_status_enum",
        ),
        nullable=False,
    )

    final_price = db.Column(db.Numeric(10, 2))
    closed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    item = db.relationship("Item", back_populates="auctions")
    seller = db.relationship("User", foreign_keys=[seller_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    bids = db.relationship("Bid", back_populates="auction", lazy="dynamic")
    sale = db.relationship("Sale", back_populates="auction", uselist=False)

    def __repr__(self):
        return f"<Auction {self.auction_id} item={self.item_id} status={self.status}>"


class Bid(db.Model):
    __tablename__ = "bids"

    bid_id = db.Column(db.Integer, primary_key=True)

    auction_id = db.Column(
        db.Integer,
        db.ForeignKey("auctions.auction_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    bidder_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    bid_amount = db.Column(db.Numeric(10, 2), nullable=False)
    max_auto_bid = db.Column(db.Numeric(10, 2))
    is_auto = db.Column(db.Boolean, nullable=False, default=False)

    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    auction = db.relationship("Auction", back_populates="bids")
    bidder = db.relationship("User", back_populates="bids")

    def __repr__(self):
        return (
            f"<Bid {self.bid_id} auction={self.auction_id} "
            f"bidder={self.bidder_id} amount={self.bid_amount}>"
        )


class Alert(db.Model):
    __tablename__ = "alerts"

    alert_id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    category = db.Column(
        db.Enum("console", "game", "accessory", name="alert_category_enum")
    )
    platform = db.Column(db.String(50))
    brand = db.Column(db.String(100))
    min_price = db.Column(db.Numeric(10, 2))
    max_price = db.Column(db.Numeric(10, 2))
    item_condition = db.Column(
        db.Enum(
            "new",
            "like_new",
            "good",
            "fair",
            "poor",
            name="alert_condition_enum",
        )
    )
    keyword = db.Column(db.String(100))

    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    user = db.relationship("User", back_populates="alerts")

    def __repr__(self):
        return f"<Alert {self.alert_id} user={self.user_id}>"

class SupportRequest(db.Model):
    __tablename__ = "support_requests"

    request_id = db.Column(db.Integer, primary_key=True)
    
    user_id = db.Column(
    MySQL_INTEGER(unsigned=True),
    db.ForeignKey("users.user_id"),
    nullable=False,
    )
    user = db.relationship("User", foreign_keys=[user_id])

    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)

    rep_id = db.Column(
    MySQL_INTEGER(unsigned=True),
    db.ForeignKey("users.user_id"),
    )
    rep = db.relationship("User", foreign_keys=[rep_id])

    response = db.Column(db.Text)

    status = db.Column(db.String(20), default="open")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)


class Sale(db.Model):
    __tablename__ = "sales"

    sale_id = db.Column(db.Integer, primary_key=True)

    auction_id = db.Column(
        db.Integer,
        db.ForeignKey("auctions.auction_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        unique=True,
    )
    item_id = db.Column(
        db.Integer,
        db.ForeignKey("items.item_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    buyer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )
    seller_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    sale_price = db.Column(db.Numeric(10, 2), nullable=False)
    sold_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    auction = db.relationship("Auction", back_populates="sale")
    item = db.relationship("Item", back_populates="sales")
    buyer = db.relationship("User", foreign_keys=[buyer_id])
    seller = db.relationship("User", foreign_keys=[seller_id])

    def __repr__(self):
        return (
            f"<Sale {self.sale_id} auction={self.auction_id} "
            f"buyer={self.buyer_id} seller={self.seller_id} "
            f"price={self.sale_price}>"
        )
    
