"""Centro de notificaciones común para todos los perfiles."""

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from compras_models import PurchaseNotification
from fase5_forms import ActionFormFase5
from models import db


notificaciones_bp = Blueprint(
    "notificaciones", __name__, url_prefix="/notificaciones"
)


@notificaciones_bp.get("/")
@login_required
def lista():
    notifications = (
        PurchaseNotification.query.filter_by(user_id=current_user.id)
        .order_by(PurchaseNotification.created_at.desc())
        .limit(250)
        .all()
    )
    return render_template(
        "notificaciones/lista.html",
        notifications=notifications,
        action_form=ActionFormFase5(),
    )


@notificaciones_bp.post("/<int:notification_id>/leer")
@login_required
def leer(notification_id):
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    notification = db.get_or_404(PurchaseNotification, notification_id)
    if notification.user_id != current_user.id:
        abort(404)
    notification.leida = True
    db.session.commit()
    destination = notification.enlace or url_for("notificaciones.lista")
    if not destination.startswith("/") or destination.startswith("//"):
        destination = url_for("notificaciones.lista")
    return redirect(destination)


@notificaciones_bp.post("/leer-todas")
@login_required
def leer_todas():
    form = ActionFormFase5()
    if not form.validate_on_submit():
        abort(400)
    PurchaseNotification.query.filter_by(
        user_id=current_user.id, leida=False
    ).update({"leida": True}, synchronize_session=False)
    db.session.commit()
    return redirect(url_for("notificaciones.lista"))
