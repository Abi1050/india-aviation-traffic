"""Assemble report inputs from the current session (shared by the Future Forecast and Reports pages)."""

from __future__ import annotations

import streamlit as st

from config.settings import TRAFFIC_COLUMNS
from src import diagnostics as dg, eda, forecasting as fc, reporting, state


def future_forecast(ctx: state.Context):
    """(result, model, reason, error) for the official future forecast."""
    evaluation, _ = state.get_evaluation(ctx)
    model, reason = state.resolve_future_model(ctx, evaluation)
    result, err = state.get_forecast(ctx, model)
    return result, model, reason, err


def assemble(ctx: state.Context) -> dict:
    q = ctx.quarterly
    evaluation, eval_err = state.get_evaluation(ctx)
    result, model, reason, ferr = future_forecast(ctx)
    checks = fc.validate_forecast(result.forecast, q[ctx.target].dropna().index, ctx.horizon) if result else None
    residuals = None
    if result is not None:
        summary = dg.residual_summary(result.residuals)
        try:
            lb = dg.ljung_box(result.residuals, [4, 8])
        except ValueError:
            lb = None
        residuals = {"model": result.model, "scale": result.residual_scale, "summary": summary, "ljung_box": lb,
                     "note": dg.small_sample_note(summary["N"])}
    complete = q[TRAFFIC_COLUMNS].dropna()
    s = st.session_state
    return reporting.build_report_data(
        bundle=ctx.bundle, quarterly=q, filter_note=ctx.filter_note, target=ctx.target, horizon=ctx.horizon,
        ci=ctx.ci, period=ctx.period,
        model_settings={"sarimax": state.sarimax_config(ctx.period).label(), "var": state.var_config().label(),
                        "evaluation_models": ", ".join(s["ev_models"]), "evaluation_quarters": s["ev_test_size"]},
        stats=eda.descriptive_statistics(q, TRAFFIC_COLUMNS),
        adf=dg.adf_table(q, TRAFFIC_COLUMNS, ["Level", "First difference"], 0.05, ctx.period),
        corr=eda.correlation_matrix(complete, TRAFFIC_COLUMNS) if len(complete) > 2 else None,
        evaluation=evaluation, eval_error=eval_err, metric=s["ev_metric"],
        forecast=result, forecast_model=model, forecast_reason=reason, forecast_checks=checks, forecast_error=ferr,
        residuals=residuals, insights=eda.series_insights(q, ctx.target),
    )
