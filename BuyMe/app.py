from datetime import datetime, timedelta
from sqlalchemy import case, func, or_


from flask import (
    Flask,
    request,
    redirect,
    url_for,
    session,
    render_template,
)
from werkzeug.security import generate_password_hash, check_password_hash

# Adjust this import if your structure is different
from model.models import db, User, Item, Auction, Bid, Alert, Sale, SupportRequest




app = Flask(__name__)

# Needed for sessions (login/logout)
app.config["SECRET_KEY"] = "dev-change-this-later"

# DB config
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "mysql+pymysql://buyme_user:buyme_pass@localhost/gaming_marketplace"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)



def get_current_user():
    """Return the logged-in User object or None."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    return User.query.get(user_id)

def count_alert_matches_for_user(user):
    """Return how many running auctions match this user's alerts."""
    if not user:
        return 0

    alerts = Alert.query.filter_by(user_id=user.user_id).all()
    total_matches = 0

    for alert in alerts:
        q = (
            db.session.query(Auction)
            .join(Item, Auction.item_id == Item.item_id)
            .filter(Auction.status == "running")
        )

        if alert.category:
            q = q.filter(Item.category == alert.category)

        if alert.min_price is not None:
            q = q.filter(Auction.current_price >= alert.min_price)

        if alert.max_price is not None:
            q = q.filter(Auction.current_price <= alert.max_price)

        if alert.brand:
            q = q.filter(Item.brand.ilike(f"%{alert.brand}%"))

        if getattr(alert, "platform", None):
            q = q.filter(Item.platform.ilike(f"%{alert.platform}%"))

        if getattr(alert, "item_condition", None):
            q = q.filter(Item.item_condition == alert.item_condition)

        # Add the number of matching auctions for this alert
        total_matches += q.count()

    return total_matches

def require_rep_or_admin():
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return None, ("You do not have permission to access this page.", 403)
    return user, None

@app.context_processor
def inject_current_user():
    u = get_current_user()
    return {"current_user": u, "user": u}


def compute_minimum_bid(auction: Auction) -> float:
    """
    Minimum legal bid:
    - If no bids yet: at least starting_price.
    - If bids exist: highest bid_amount + bid_increment.
    """
    highest_bid = auction.bids.order_by(Bid.bid_amount.desc()).first()
    if highest_bid is None:
        return float(auction.starting_price)
    return float(highest_bid.bid_amount) + float(auction.bid_increment)

@app.route("/rep/users")
def rep_users():
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to access this page.", 403

    query = (request.args.get("q") or "").strip()

    results = []
    if query:
        like = f"%{query}%"
        results = (
            User.query
            .filter(
                or_(
                    User.username.ilike(like),
                    User.email.ilike(like),
                )
            )
            .order_by(User.created_at.desc())
            .all()
        )

    return render_template(
        "rep_users.html",
        query=query,
        results=results,
    )

@app.route("/rep/users/<int:user_id>/reset-password", methods=["GET", "POST"])
def rep_reset_password(user_id):
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to access this page.", 403

    target = User.query.get_or_404(user_id)

    if request.method == "GET":
        return render_template("rep_reset_password.html", target=target)

    # POST: actually reset
    new_password = (request.form.get("new_password") or "").strip()
    if not new_password:
        return render_template(
            "rep_reset_password.html",
            target=target,
            error_message="New password cannot be empty.",
        )

    target.password_hash = generate_password_hash(new_password)
    db.session.commit()

    return render_template(
        "rep_reset_password.html",
        target=target,
        success_message="Password has been reset successfully.",
    )
@app.route("/rep/auctions")
def rep_auctions():
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to access this page.", 403

    status = (request.args.get("status") or "").strip()
    seller = (request.args.get("seller") or "").strip()

    q = Auction.query

    if status:
        q = q.filter(Auction.status == status)

    if seller:
        like = f"%{seller}%"
        q = q.join(User, Auction.seller_id == User.user_id).filter(
            User.username.ilike(like)
        )

    auctions = q.order_by(Auction.created_at.desc()).limit(100).all()

    return render_template(
        "rep_auctions.html",
        auctions=auctions,
        status=status,
        seller=seller,
    )

@app.route("/rep/auctions/<int:auction_id>/cancel", methods=["POST"])
def rep_cancel_auction(auction_id):
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to perform this action.", 403

    auction = Auction.query.get_or_404(auction_id)

    if auction.status in ("ended", "cancelled"):
        # Nothing to do
        return redirect(url_for("rep_auctions"))

    auction.status = "cancelled"
    auction.closed_at = datetime.now()
    db.session.commit()

    return redirect(url_for("rep_auctions"))


def update_auction_from_highest_bid(auction: Auction) -> None:
    """
    Set current_price and winner_id based on the highest bid_amount.
    If there are no bids, fall back to starting_price and no winner.
    """
    highest_bid = auction.bids.order_by(
        Bid.bid_amount.desc(), Bid.created_at.desc()
    ).first()

    if highest_bid is None:
        auction.current_price = auction.starting_price
        auction.winner_id = None
    else:
        auction.current_price = highest_bid.bid_amount
        auction.winner_id = highest_bid.bidder_id

def ensure_admin_user():
    admin = User.query.filter_by(username="admin").first()
    if not admin:
        admin = User(
            username="admin",
            email="admin@example.com",
            role="admin",
            password_hash=generate_password_hash("admin123"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.session.add(admin)
        db.session.commit()
        print("Created default admin user: admin / admin123")

@app.route("/admin/create_rep", methods=["GET", "POST"])
def create_rep():
    user = get_current_user()
    if not user or user.role != "admin":
        return "You do not have permission to access this page.", 403

    if request.method == "GET":
        return render_template("create_rep.html")

    # POST: handle form submission
    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()
    password = (request.form.get("password") or "").strip()

    if not username or not email or not password:
        return render_template(
            "create_rep.html",
            error_message="All fields are required.",
        )

    # Check if username or email already exists
    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        return render_template(
            "create_rep.html",
            error_message="A user with that username or email already exists.",
        )

    rep = User(
        username=username,
        email=email,
        role="rep",
        password_hash=generate_password_hash(password),
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db.session.add(rep)
    db.session.commit()

    return render_template(
        "create_rep.html",
        success_message=f"Customer representative '{username}' has been created.",
    )

# LANDING PAGE
@app.route("/")
def index():
    user = get_current_user()
    alert_match_count = 0

    if user:
        alert_match_count = count_alert_matches_for_user(user)

    return render_template(
        "index.html",
        user=user,
        alert_match_count=alert_match_count,
    )





@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    username = (request.form.get("username") or "").strip()
    email = (request.form.get("email") or "").strip()
    full_name = (request.form.get("full_name") or "").strip()
    password = request.form.get("password") or ""
    confirm_password = request.form.get("confirm_password") or ""

    # Missing fields
    if not username or not email or not password:
        return render_template(
            "register.html",
            error_message="Username, email, and password are required.",
        )

    # Password mismatch
    if password != confirm_password:
        return render_template(
            "register.html",
            error_message="Passwords do not match.",
        )

    # Existing username/email
    existing = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    if existing:
        return render_template(
            "register.html",
            error_message="That username or email is already in use.",
        )

    # Create user
    hashed = generate_password_hash(password)
    new_user = User(
        username=username,
        email=email,
        full_name=full_name,
        password_hash=hashed,
    )

    db.session.add(new_user)
    db.session.commit()

    session["user_id"] = new_user.user_id
    return redirect(url_for("index"))




@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""

    if not username or not password:
        return render_template(
            "login.html",
            error_message="Please enter both username and password.",
        )

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password_hash, password):
        return render_template(
            "login.html",
            error_message="Invalid username or password.",
        )

    session["user_id"] = user.user_id
    return redirect(url_for("index"))




@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/account/delete", methods=["POST"])
def delete_account():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    impacted_auctions = set()

    user_bids = Bid.query.filter_by(bidder_id=user.user_id).all()
    for bid in user_bids:
        impacted_auctions.add(bid.auction_id)
        db.session.delete(bid)  

   
    user_auctions = Auction.query.filter_by(seller_id=user.user_id).all()
    for auction in user_auctions:
        
        auction.status = "cancelled"
        auction.closed_at = datetime.utcnow()
        impacted_auctions.add(auction.auction_id)

    
    user_alerts = Alert.query.filter_by(user_id=user.user_id).all()
    for alert in user_alerts:
        db.session.delete(alert)

   
    user_requests = SupportRequest.query.filter_by(user_id=user.user_id).all()
    for req in user_requests:
        db.session.delete(req)

   
    db.session.delete(user)

   
    db.session.commit()

    for auction_id in impacted_auctions:
        auction = Auction.query.get(auction_id)
        if not auction:
            continue
        # Only recompute for non-cancelled auctions
        if auction.status in ("running", "scheduled", "ended"):
            recompute_auction_price_and_winner(auction)

    db.session.commit()

    session.clear()
    return redirect(url_for("index"))



@app.route("/me")
def me():
    user = get_current_user()
    if not user:
        return "Not logged in"
    return (
        f"Logged in as {user.username} "
        f"(id={user.user_id}, role={user.role}, email={user.email})"
    )

@app.route("/support", methods=["GET", "POST"])
def support():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        subject = (request.form.get("subject") or "").strip()
        message = (request.form.get("message") or "").strip()

        if not subject or not message:
            return render_template(
                "support.html",
                error_message="Subject and message are required.",
            )

        req = SupportRequest(
            user_id=user.user_id,
            subject=subject,
            message=message,
            status="open",
            created_at=datetime.utcnow(),
        )
        db.session.add(req)
        db.session.commit()

        return render_template(
            "support.html",
            success_message="Your request has been submitted.",
        )

    return render_template("support.html")

@app.route("/support/my")
def my_support_requests():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    requests = (
        SupportRequest.query
        .filter_by(user_id=user.user_id)
        .order_by(SupportRequest.created_at.desc())
        .all()
    )

    return render_template("support_my.html", requests=requests)

@app.route("/rep/support")
def rep_support_list():
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to view this page.", 403

    requests = (
        SupportRequest.query
        .order_by(SupportRequest.status.asc(), SupportRequest.created_at.desc())
        .all()
    )

    return render_template("rep_support.html", requests=requests)

@app.route("/rep/support/<int:request_id>", methods=["GET", "POST"])
def rep_support_detail(request_id):
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to view this page.", 403

    req = SupportRequest.query.get_or_404(request_id)

    if request.method == "POST":
        response_text = (request.form.get("response") or "").strip()

        if not response_text:
            return render_template(
                "rep_support_detail.html",
                req=req,
                error_message="Response cannot be empty.",
            )

        req.rep_id = user.user_id
        req.response = response_text
        req.status = "resolved"
        req.responded_at = datetime.utcnow()

        db.session.commit()

        return redirect(url_for("rep_support_list"))

    # GET: show the request + any existing response
    return render_template("rep_support_detail.html", req=req)


@app.route("/items/new", methods=["GET", "POST"])
def create_item():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("create_item.html")

    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    category = (request.form.get("category") or "").strip()
    brand = (request.form.get("brand") or "").strip()
    platform = (request.form.get("platform") or "").strip()
    color = (request.form.get("color") or "").strip()
    item_condition = (request.form.get("item_condition") or "").strip()
    base_price_raw = (request.form.get("base_price") or "").strip()

    storage_capacity = (request.form.get("storage_capacity") or "").strip()
    console_model = (request.form.get("console_model") or "").strip()

    genre = (request.form.get("genre") or "").strip()
    age_rating = (request.form.get("age_rating") or "").strip()
    edition = (request.form.get("edition") or "").strip()

    accessory_type = (request.form.get("accessory_type") or "").strip()
    wireless = request.form.get("wireless") == "1"

    # Category-specific required fields
    if category == "console":
        if not storage_capacity or not console_model:
            return render_template(
                "create_item.html",
                error_message="For console items, storage capacity and console model are required.",
            )

    elif category == "game":
        if not genre or not age_rating or not edition:
            return render_template(
                "create_item.html",
                error_message="For game items, genre, age rating, and edition are required.",
            )

    elif category == "accessory":
        if not accessory_type:
            return render_template(
                "create_item.html",
                error_message="For accessory items, accessory type is required.",
            )

    # Basic required fields
    if not title or not category or not item_condition or not base_price_raw:
        return render_template(
            "create_item.html",
            error_message="Title, category, condition, and base price are required.",
        )

    try:
        base_price = float(base_price_raw)
    except ValueError:
        return render_template(
            "create_item.html",
            error_message="Invalid base price.",
        )

    new_item = Item(
        seller_id=user.user_id,
        title=title,
        description=description or None,
        category=category,
        brand=brand or None,
        platform=platform or None,
        color=color or None,
        item_condition=item_condition,
        base_price=base_price,
        storage_capacity=storage_capacity or None,
        console_model=console_model or None,
        genre=genre or None,
        age_rating=age_rating or None,
        edition=edition or None,
        accessory_type=accessory_type or None,
        wireless=wireless,
        created_at=datetime.utcnow(),
    )

    db.session.add(new_item)
    db.session.commit()

    return redirect(url_for("view_item", item_id=new_item.item_id))



@app.route("/items/<int:item_id>")
def view_item(item_id):
    item = Item.query.get_or_404(item_id)
    seller = item.seller

    # Find current running auction (if any)
    active_auction = (
        Auction.query
        .filter(
            Auction.item_id == item.item_id,
            Auction.status == "running",
        )
        .order_by(Auction.end_time.asc())
        .first()
    )

    # Find past/other auctions for this item
    other_auctions = (
        Auction.query
        .filter(
            Auction.item_id == item.item_id,
            Auction.status != "running",
        )
        .order_by(Auction.end_time.desc())
        .all()
    )

    return render_template(
        "item_detail.html",
        item=item,
        seller=seller,
        active_auction=active_auction,
        other_auctions=other_auctions,
    )



@app.route("/auctions/new", methods=["GET", "POST"])
def create_auction():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    item_id_raw = (
        request.args.get("item_id")
        if request.method == "GET"
        else request.form.get("item_id")
    )

    if not item_id_raw:
        return "Missing item_id", 400

    try:
        item_id = int(item_id_raw)
    except ValueError:
        return "Invalid item_id", 400

    item = Item.query.get_or_404(item_id)

    # Only the seller of the item can create an auction
    if item.seller_id != user.user_id:
        return "You are not the seller of this item", 403

    # Prevent multiple active auctions for same item
    active_auction = (
        Auction.query
        .filter(
            Auction.item_id == item.item_id,
            Auction.status.in_(["scheduled", "running"])
        )
        .first()
    )

    if active_auction:
        # Show message, do not allow new auction
        return render_template(
            "create_auction.html",
            item=item,
            active_auction=active_auction,
            blocked=True,
        )

    if request.method == "GET":
        return render_template("create_auction.html", item=item, blocked=False)

    starting_price_raw = (request.form.get("starting_price") or "").strip()
    bid_increment_raw = (request.form.get("bid_increment") or "").strip()
    secret_min_price_raw = (request.form.get("secret_min_price") or "").strip()
    buy_now_price_raw = (request.form.get("buy_now_price") or "").strip()
    duration_hours_raw = (request.form.get("duration_hours") or "").strip() or "24"

    try:
        starting_price = float(starting_price_raw)
        bid_increment = float(bid_increment_raw)
        secret_min_price = float(secret_min_price_raw)
        duration_hours = float(duration_hours_raw)
    except ValueError:
        return render_template(
            "create_auction.html",
            item=item,
            blocked=False,
            error_message="Invalid numeric value in auction form.",
        )

    buy_now_price = None
    if buy_now_price_raw:
        try:
            buy_now_price = float(buy_now_price_raw)
        except ValueError:
            return render_template(
                "create_auction.html",
                item=item,
                blocked=False,
                error_message="Invalid buy now price.",
            )

    start_time = datetime.utcnow()
    end_time = start_time + timedelta(hours=duration_hours)

    auction = Auction(
        item_id=item.item_id,
        seller_id=user.user_id,
        winner_id=None,
        start_time=start_time,
        end_time=end_time,
        starting_price=starting_price,
        current_price=starting_price,
        bid_increment=bid_increment,
        secret_min_price=secret_min_price,
        buy_now_price=buy_now_price,
        status="running",  # or "scheduled" if you later add future start times
        final_price=None,
        closed_at=None,
        created_at=datetime.utcnow(),
    )

    db.session.add(auction)
    db.session.commit()

    return redirect(url_for("view_auction", auction_id=auction.auction_id))


@app.route("/auctions/<int:auction_id>")
def view_auction(auction_id):
    auction = Auction.query.get_or_404(auction_id)
    item = auction.item
    seller = auction.seller
    winner = auction.winner

    min_bid = compute_minimum_bid(auction)

    # Bid history (newest first)
    bids = auction.bids.order_by(Bid.created_at.desc()).all()

    # Buy Now visibility
    show_buy_now_button = False
    if auction.buy_now_price is not None and auction.status == "running":
        threshold = 0.8 * float(auction.buy_now_price)
        if float(auction.current_price) < threshold:
            show_buy_now_button = True

    # Similar items query
    lower_price = float(auction.current_price) * 0.7
    upper_price = float(auction.current_price) * 1.3

    similar_auctions = (
        Auction.query
        .join(Item)
        .filter(
            Item.category == item.category,
            Auction.auction_id != auction.auction_id,
            Auction.current_price >= lower_price,
            Auction.current_price <= upper_price,
        )
        .order_by(
            # Same brand as current item first
            case(
                (Item.brand == item.brand, 0),
                else_=1,
            ),
            # Then by closeness in price
            func.abs(Auction.current_price - auction.current_price),
        )
        .limit(5)
        .all()
    )

    return render_template(
        "auction_detail.html",
        auction=auction,
        item=item,
        seller=seller,
        winner=winner,
        min_bid=min_bid,
        bids=bids,
        similar_auctions=similar_auctions,
        show_buy_now_button=show_buy_now_button,
    )


@app.route("/auctions/<int:auction_id>/bid", methods=["POST"])
def place_bid(auction_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    auction = Auction.query.get_or_404(auction_id)

    if auction.seller_id == user.user_id:
        return "You cannot bid on your own auction.", 400
    
    now = datetime.utcnow()
    if auction.status != "running" or now < auction.start_time or now > auction.end_time:
        return "Auction not open for bidding", 400

    bid_amount_raw = (request.form.get("bid_amount") or "").strip()
    max_auto_bid_raw = (request.form.get("max_auto_bid") or "").strip()

    if not bid_amount_raw:
        return "Missing bid amount", 400

    try:
        bid_amount = float(bid_amount_raw)
    except ValueError:
        return "Invalid bid amount", 400

    max_auto_bid = None
    if max_auto_bid_raw:
        try:
            max_auto_bid = float(max_auto_bid_raw)
        except ValueError:
            return "Invalid max auto-bid amount", 400

    # Enforce minimum
    min_allowed = compute_minimum_bid(auction)
    if bid_amount < min_allowed:
        return f"Bid too low. Minimum allowed is {min_allowed}", 400

    if max_auto_bid is not None and max_auto_bid < bid_amount:
        return "max_auto_bid must be >= your bid amount", 400

    # 1) Save the user's manual bid
    new_bid = Bid(
        auction_id=auction.auction_id,
        bidder_id=user.user_id,
        bid_amount=bid_amount,
        max_auto_bid=max_auto_bid,
        is_auto=False,
        created_at=datetime.utcnow(),
    )
    db.session.add(new_bid)
    db.session.flush()  # include in auction.bids

    # 2) AUTO-BID based on caps
    caps = {}  # bidder_id -> cap
    for b in auction.bids.all():
        cap = b.max_auto_bid if b.max_auto_bid is not None else b.bid_amount
        prev = caps.get(b.bidder_id)
        if prev is None or cap > prev:
            caps[b.bidder_id] = cap

    cap_new = caps.get(user.user_id, bid_amount)

    auto_bidder_id = None
    auto_cap = None
    for bidder_id, cap in caps.items():
        if bidder_id == user.user_id:
            continue
        if auto_cap is None or cap > auto_cap:
            auto_cap = cap
            auto_bidder_id = bidder_id

    if auto_bidder_id is not None and auto_cap is not None and auto_cap >= bid_amount:
        auto_price = float(auto_cap)
        if auto_price > bid_amount:
            auto_bid = Bid(
                auction_id=auction.auction_id,
                bidder_id=auto_bidder_id,
                bid_amount=auto_price,
                max_auto_bid=auto_cap,
                is_auto=True,
                created_at=datetime.utcnow(),
            )
            db.session.add(auto_bid)

    # 3) Update auction's current price and winner
    update_auction_from_highest_bid(auction)

    db.session.commit()

    return redirect(url_for("view_auction", auction_id=auction.auction_id))


@app.route("/auctions/<int:auction_id>/buy_now", methods=["POST"])
def buy_now(auction_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    auction = Auction.query.get_or_404(auction_id)

    if auction.buy_now_price is None:
        return "Buy Now not available for this auction", 400

    now = datetime.utcnow()
    if auction.status != "running" or now < auction.start_time or now > auction.end_time:
        return "Auction not open for Buy Now", 400

    threshold = 0.8 * float(auction.buy_now_price)
    if float(auction.current_price) >= threshold:
        return "Buy Now option is no longer available", 400

    if auction.seller_id == user.user_id:
        return "Seller cannot use Buy Now on their own auction", 400

    # Record a final buy-now bid
    buy_now_bid = Bid(
        auction_id=auction.auction_id,
        bidder_id=user.user_id,
        bid_amount=auction.buy_now_price,
        max_auto_bid=auction.buy_now_price,
        is_auto=False,
        created_at=datetime.utcnow(),
    )
    db.session.add(buy_now_bid)

    auction.current_price = auction.buy_now_price
    auction.winner_id = user.user_id
    auction.status = "ended"
    auction.final_price = auction.buy_now_price
    auction.closed_at = datetime.utcnow()

    db.session.commit()

    return redirect(url_for("view_auction", auction_id=auction.auction_id))

@app.route("/alerts/new", methods=["GET", "POST"])
def create_alert():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "GET":
        return render_template("create_alert.html")

    # POST: create alert
    category = (request.form.get("category") or "").strip() or None
    platform = (request.form.get("platform") or "").strip() or None
    brand = (request.form.get("brand") or "").strip() or None
    min_price_raw = (request.form.get("min_price") or "").strip()
    max_price_raw = (request.form.get("max_price") or "").strip()
    item_condition = (request.form.get("item_condition") or "").strip() or None
    keyword = (request.form.get("keyword") or "").strip() or None

    min_price = None
    max_price = None
    if min_price_raw:
        try:
            min_price = float(min_price_raw)
        except ValueError:
            return render_template(
                "create_alert.html",
                error_message="Invalid minimum price.",
            )

    if max_price_raw:
        try:
            max_price = float(max_price_raw)
        except ValueError:
            return render_template(
                "create_alert.html",
                error_message="Invalid maximum price.",
            )

    alert = Alert(
        user_id=user.user_id,
        category=category,
        platform=platform,
        brand=brand,
        min_price=min_price,
        max_price=max_price,
        item_condition=item_condition,
        keyword=keyword,
        is_active=True,
    )

    db.session.add(alert)
    db.session.commit()

    return redirect(url_for("list_alerts"))


@app.route("/alerts")
def list_alerts():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    alerts = (
        Alert.query
        .filter_by(user_id=user.user_id, is_active=True)
        .order_by(Alert.created_at.desc())
        .all()
    )

    return render_template("alerts.html", alerts=alerts)


@app.route("/alerts/<int:alert_id>/matches")
def view_alert_matches(alert_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    alert = Alert.query.get_or_404(alert_id)

    # Ensure user owns this alert
    if alert.user_id != user.user_id:
        return "You do not have access to this alert.", 403

    # Base query: running auctions only
    q = (
        Auction.query
        .join(Item)
        .filter(Auction.status == "running")
    )

    # Apply filters from alert
    if alert.category:
        q = q.filter(Item.category == alert.category)

    if alert.min_price is not None:
        q = q.filter(Auction.current_price >= alert.min_price)

    if alert.max_price is not None:
        q = q.filter(Auction.current_price <= alert.max_price)

    if alert.brand:
        q = q.filter(Item.brand.ilike(f"%{alert.brand}%"))

    if alert.platform:
        q = q.filter(Item.platform.ilike(f"%{alert.platform}%"))

    if alert.item_condition:
        q = q.filter(Item.item_condition == alert.item_condition)

    if alert.keyword:
        # match in title OR description
        q = q.filter(
            or_(
                Item.title.ilike(f"%{alert.keyword}%"),
                Item.description.ilike(f"%{alert.keyword}%"),
            )
        )

    matches = q.order_by(Auction.current_price.asc()).all()

    return render_template(
        "alert_matches.html",
        alert=alert,
        matches=matches,
    )


@app.route("/alerts/<int:alert_id>/delete", methods=["POST"])
def delete_alert(alert_id):
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    alert = Alert.query.get_or_404(alert_id)
    if alert.user_id != user.user_id:
        return "You do not have access to this alert.", 403

    alert.is_active = False
    db.session.commit()

    return redirect(url_for("list_alerts"))


@app.route("/items")
def list_items():
    category = (request.args.get("category") or "").strip()
    platform = (request.args.get("platform") or "").strip()
    brand = (request.args.get("brand") or "").strip()
    condition = (request.args.get("condition") or "").strip()
    min_price = (request.args.get("min_price") or "").strip()
    max_price = (request.args.get("max_price") or "").strip()

    # Base query: left join items with auctions
    q = (
        db.session.query(Item, Auction)
        .outerjoin(Auction, Item.item_id == Auction.item_id)
    )

    # Apply filters
    if category:
        q = q.filter(Item.category == category)

    if platform:
        # case-insensitive contains match
        q = q.filter(Item.platform.ilike(f"%{platform}%"))

    if brand:
        q = q.filter(Item.brand.ilike(f"%{brand}%"))

    if condition:
        q = q.filter(Item.item_condition == condition)

    # Price range: filter on base_price (simple and good enough)
    try:
        if min_price:
            q = q.filter(Item.base_price >= float(min_price))
        if max_price:
            q = q.filter(Item.base_price <= float(max_price))
    except ValueError:
        # If user types nonsense in price, just ignore the price filter
        pass

    items = q.order_by(Item.created_at.desc()).all()

    filters = {
        "category": category,
        "platform": platform,
        "brand": brand,
        "condition": condition,
        "min_price": min_price,
        "max_price": max_price,
    }

    return render_template("items_list.html", items=items, filters=filters)



@app.route("/my_items")
def my_items():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    # Get all items for this seller
    items = (
        Item.query
        .filter(Item.seller_id == user.user_id)
        .order_by(Item.created_at.desc())
        .all()
    )

    # For each item, find an active auction (running or scheduled), if any
    item_rows = []
    for item in items:
        active = None
        for a in item.auctions:
            if a.status in ("running", "scheduled"):
                active = a
                break
        item_rows.append((item, active))

    # items is now a list of (item, active_auction) tuples
    return render_template("my_items.html", items=item_rows)



@app.route("/my/bids")
def my_bids():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    bids = (
        Bid.query
        .filter(Bid.bidder_id == user.user_id)
        .order_by(Bid.created_at.desc())
        .all()
    )

    return render_template("my_bids.html", bids=bids)

@app.route("/my/auctions")
def my_auctions():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    auctions = (
        Auction.query
        .filter(Auction.seller_id == user.user_id)
        .order_by(Auction.created_at.desc())
        .all()
    )

    return render_template("my_auctions.html", auctions=auctions)

@app.route("/rep/bids")
def rep_bids():
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to access this page.", 403

    bidder = (request.args.get("bidder") or "").strip()
    auction_id = (request.args.get("auction_id") or "").strip()

    q = Bid.query.join(User, Bid.bidder_id == User.user_id)

    if bidder:
        like = f"%{bidder}%"
        q = q.filter(User.username.ilike(like))

    if auction_id:
        try:
            aid = int(auction_id)
            q = q.filter(Bid.auction_id == aid)
        except ValueError:
            pass

    bids = q.order_by(Bid.created_at.desc()).limit(200).all()

    return render_template(
        "rep_bids.html",
        bids=bids,
        bidder=bidder,
        auction_id=auction_id,
    )

def recompute_auction_price_and_winner(auction):
    remaining_bids = (
        Bid.query
        .filter(Bid.auction_id == auction.auction_id)
        .order_by(Bid.bid_amount.desc(), Bid.created_at.asc())
        .all()
    )

    if remaining_bids:
        top = remaining_bids[0]
        auction.current_price = top.bid_amount
        auction.winner_id = top.bidder_id
    else:
        auction.current_price = auction.starting_price
        auction.winner_id = None

@app.route("/rep/bids/<int:bid_id>/delete", methods=["POST"])
def rep_delete_bid(bid_id):
    user = get_current_user()
    if not user or user.role not in ("rep", "admin"):
        return "You do not have permission to perform this action.", 403

    bid = Bid.query.get_or_404(bid_id)
    auction = bid.auction

    db.session.delete(bid)

    remaining_bids = (
        Bid.query
        .filter(Bid.auction_id == auction.auction_id)
        .order_by(Bid.bid_amount.desc(), Bid.created_at.asc())
        .all()
    )

    if remaining_bids:
        top = remaining_bids[0]
        auction.current_price = top.bid_amount
        auction.winner_id = top.bidder_id
    else:
        auction.current_price = auction.starting_price
        auction.winner_id = None

    db.session.commit()

    return redirect(url_for("rep_bids"))


@app.route("/admin/reports")
def admin_reports():
    user = get_current_user()
    if not user or user.role != "admin":
        return "You do not have permission to view this page.", 403

    total_earnings = (
        db.session.query(func.coalesce(func.sum(Sale.sale_price), 0))
        .scalar()
    )

    earnings_by_category = (
        db.session.query(
            Item.category,
            func.sum(Sale.sale_price).label("total_revenue"),
            func.count(Sale.sale_id).label("num_sales"),
        )
        .join(Item, Sale.item_id == Item.item_id)
        .group_by(Item.category)
        .order_by(func.sum(Sale.sale_price).desc())
        .all()
    )
    earnings_by_seller = (
        db.session.query(
            User.user_id,
            User.username,
            func.sum(Sale.sale_price).label("total_revenue"),
            func.count(Sale.sale_id).label("num_sales"),
        )
        .join(User, Sale.seller_id == User.user_id)
        .group_by(User.user_id, User.username)
        .order_by(func.sum(Sale.sale_price).desc())
        .all()
    )

    top_items = (
        db.session.query(
            Item.item_id,
            Item.title,
            Item.category,
            func.sum(Sale.sale_price).label("total_revenue"),
            func.count(Sale.sale_id).label("num_sales"),
        )
        .join(Item, Sale.item_id == Item.item_id)
        .group_by(Item.item_id, Item.title, Item.category)
        .order_by(func.sum(Sale.sale_price).desc())
        .limit(10)
        .all()
    )

    return render_template(
        "admin_reports.html",
        total_earnings=total_earnings,
        earnings_by_category=earnings_by_category,
        earnings_by_seller=earnings_by_seller,
        top_items=top_items,
    )

@app.route("/account", methods=["GET", "POST"])
def account():
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    if request.method == "POST":
        confirm_text = (request.form.get("confirm_text") or "").strip()
        if confirm_text != "DELETE":
            return render_template(
                "account.html",
                user=user,
                error_message="To delete your account, type DELETE in the confirmation box.",
            )

        username = user.username  # keep for message

        session.pop("user_id", None)

        db.session.delete(user)
        db.session.commit()

        return render_template("account_deleted.html", username=username)

    return render_template("account.html", user=user)


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        ensure_admin_user()
    app.run(debug=True)

