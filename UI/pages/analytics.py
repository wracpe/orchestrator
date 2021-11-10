import io
import pandas as pd
import streamlit as st

from UI.cached_funcs import calculate_statistics_plots


def update_exclude_wells(session):
    session.exclude_wells = session.mselect_exclude_wells


def show(session):
    if not session.statistics_df_test:
        st.info('Здесь будет отображаться статистика по выбранному набору скважин.')
        return

    wells_in_model = []
    for df in session.statistics_df_test.values():
        wells_in_model.append(set([col.split('_')[0] for col in df.columns]))
    # Можно строить статистику только для общего набора скважин (скважина рассчитана всеми моделями),
    # либо для всех скважин (скважина рассчитана хотя бы одной моделью).
    # Выберите, что подать в конфиг ниже: well_names_common или well_names_all.
    well_names_all = tuple(set.union(*wells_in_model))
    well_names_common = tuple(set.intersection(*wells_in_model))
    well_names_for_statistics = well_names_all
    analytics_plots, config_stat = calculate_statistics_plots(
        statistics=session.statistics_df_test,
        field_name=session.was_config.field_name,
        date_start=session.dates_test_period[0],
        date_end=session.dates_test_period[-1],
        well_names=well_names_for_statistics,
        use_abs=False,
        exclude_wells=session.exclude_wells,
        bin_size=10
    )
    available_plots = [*analytics_plots]
    plots_to_draw = [plot_name for plot_name in available_plots
                     if plot_name not in config_stat.ignore_plots]
    stat_to_draw = st.selectbox(
        label='Статистика',
        options=sorted(plots_to_draw),
        key='stat_to_draw'
    )
    st.plotly_chart(analytics_plots[stat_to_draw], use_container_width=True)

    # Форма "Исключить скважины из статистики"
    form = st.form("form_exclude_wells")
    form.multiselect("Исключить скважины из статистики:",
                     options=sorted(well_names_for_statistics),
                     default=sorted(session.exclude_wells),
                     key="mselect_exclude_wells")
    form.form_submit_button("Применить", on_click=update_exclude_wells, args=(session,))

    # Подготовка данных к выгрузке
    if session.buffer is None:
        session.buffer = io.BytesIO()
        with pd.ExcelWriter(session.buffer) as writer:
            for key in session.statistics:
                session.statistics[key].to_excel(writer, sheet_name=key)
            if not session.ensemble_interval.empty:
                session.ensemble_interval.to_excel(writer, sheet_name='ensemble_interval')
            if session.adapt_params:
                df_adapt_params = pd.DataFrame(session.adapt_params)
                df_adapt_params.to_excel(writer, sheet_name='adapt_params')
    st.download_button(
        label="Экспорт результатов по всем скважинам",
        data=session.buffer,
        file_name=f'Все результаты {session.was_config.field_name}.xlsx',
        mime='text/csv',
    )
