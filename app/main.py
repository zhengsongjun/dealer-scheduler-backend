from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import auth, dealers, time_off, availability, ride_share, projections, schedules, admin_requests, scheduler_config, notifications

app = FastAPI(title="Dealer Manager API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(dealers.router, prefix="/api/v1/dealers", tags=["Dealers"])
app.include_router(time_off.router, prefix="/api/v1/time-off", tags=["Time Off"])
app.include_router(availability.router, prefix="/api/v1/availability", tags=["Availability"])
app.include_router(ride_share.router, prefix="/api/v1/ride-share", tags=["Ride Share"])
app.include_router(projections.router, prefix="/api/v1/projections", tags=["Projections"])
app.include_router(schedules.router, prefix="/api/v1/schedules", tags=["Schedules"])
app.include_router(admin_requests.router, prefix="/api/v1/admin/requests", tags=["Admin Requests"])
app.include_router(scheduler_config.router, prefix="/api/v1/scheduler-config", tags=["Scheduler Config"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])


@app.get("/health")
def health():
    return {"status": "ok"}
