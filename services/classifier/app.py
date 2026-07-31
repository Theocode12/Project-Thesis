"""
app.py

FastAPI entry point for the classifier service.

Accepts diagnosis requests from the orchestrator, enqueues them for
background processing, and replies immediately (202). Results are
published to MQTT once classification completes.
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from classifier import Classifier, create_classifier
from diagnosis_service import DiagnosisService

from shared.mqtt_config import MQTTConfig
from shared.mqtt_service import MQTTService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger("app")


class DiagnoseRequest(BaseModel):
    batch: list[dict]
    meta: dict = {}


def create_app(
    diagnosis_service: DiagnosisService = None,
) -> FastAPI:
    service = diagnosis_service

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if service is None:
            classifier: Classifier = create_classifier()
            mqtt_service = MQTTService(
                MQTTConfig(client_id="classifier")
            )
            mqtt_service.connect()
            mqtt_service.start()
            app.state.mqtt_service = mqtt_service
            app.state.diagnosis_service = DiagnosisService(
                classifier=classifier,
                mqtt_service=mqtt_service,
            )
        else:
            app.state.diagnosis_service = service

        app.state.diagnosis_service.start()
        log.info("Classifier service started")

        try:
            yield
        finally:
            app.state.diagnosis_service.stop()
            mqtt_service = getattr(app.state, "mqtt_service", None)
            if mqtt_service is not None:
                mqtt_service.stop()
            log.info("Classifier service stopped")

    app = FastAPI(title="Classifier Service", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/diagnose", status_code=202)
    def diagnose(request: Request, body: DiagnoseRequest) -> dict:
        if not body.batch:
            raise HTTPException(
                status_code=400,
                detail="batch must not be empty",
            )

        batch_id = request.app.state.diagnosis_service.submit(
            {
                "batch": body.batch,
                "meta": body.meta,
            }
        )
        return {"accepted": True, "batch_id": batch_id}

    return app


app = create_app()


def main() -> None:
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
