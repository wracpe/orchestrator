from datetime import date, timedelta
import streamlit as st

import UI.pages.analytics
import UI.pages.models_settings
import UI.pages.resume_app
import UI.pages.specific_well
import UI.pages.wells_map
from tools_preprocessor.config import Config as ConfigPreprocessor
from tools_preprocessor.preprocessor import Preprocessor
from UI.cached_funcs import calculate_ftor, calculate_wolfram, calculate_CRM, calculate_ensemble, run_preprocessor
from UI.config import FIELDS_SHOPS, DATE_MIN, DATE_MAX, DEFAULT_FTOR_BOUNDS
from UI.data_processor import *


def start_streamlit() -> st.session_state:
    """Возвращает инициализированную сессию streamlit.
    """
    # Мета-настройки для Streamlit
    st.set_page_config(
        page_title='КСП',
        layout="wide"  # Для отображения на всю ширину браузера
    )
    # Инициализация значений сессии st.session_state
    _session = st.session_state
    if 'date_start' not in _session:
        initialize_session(_session)
    return _session


def initialize_session(_session: st.session_state) -> None:
    """Инициализация сессии streamlit.session_state.

    - Инициализируется пустой словарь состояния программы session.state.
    - Инициализируются значения параметров моделей для страницы models_settings.py

    Notes:
        Функция используется только при первом рендеринге приложения.
    """
    _session.state = AppState()
    # Ftor model
    _session.constraints = {}
    for param_name, param_dict in DEFAULT_FTOR_BOUNDS.items():
        _session[f'{param_name}_is_adapt'] = True
        _session[f'{param_name}_lower'] = param_dict['lower_val']
        _session[f'{param_name}_default'] = param_dict['default_val']
        _session[f'{param_name}_upper'] = param_dict['upper_val']
    # ML model
    _session.estimator_name_group = 'xgb'
    _session.estimator_name_well = 'svr'
    _session.is_deep_grid_search = False
    _session.quantiles = [0.1, 0.3]
    _session.window_sizes = [3, 5, 7, 15, 30]
    # Ensemble model
    _session.ensemble_adapt_period = 28
    _session.interval_probability = 0.9
    _session.draws = 300
    _session.tune = 200
    _session.chains = 1
    _session.target_accept = 0.95


def parse_well_names(well_names_ois: List[int]) -> Tuple[Dict[str, int], Dict[int, str]]:
    """Функция сопоставляет имена скважин OIS и (ГРАД?)

    Parameters
    ----------
    well_names_ois: List[int]
        список имен скважин в формате OIS (например 245023100).

    Returns
    -------
    wellnames_key_normal : Dict[str, int]
        Ключ = имя скважины в формате ГРАД, значение - имя скважины OIS.
    wellnames_key_ois : Dict[int, str]
        Ключ = имя скважины OIS, значение - имя скважины в формате ГРАД.
    """
    welllist = pd.read_feather(Preprocessor._path_general / field_name / 'welllist.feather')
    wellnames_key_normal_ = {}
    wellnames_key_ois_ = {}
    for name_ois in well_names_ois:
        well_name_norm = welllist[welllist.ois == name_ois]
        well_name_norm = well_name_norm[well_name_norm.npath == 0]
        well_name_norm = well_name_norm.at[well_name_norm.index[0], 'num']
        wellnames_key_normal_[well_name_norm] = name_ois
        wellnames_key_ois_[name_ois] = well_name_norm
    return wellnames_key_normal_, wellnames_key_ois_


def get_current_state(state: AppState, _session: st.session_state) -> AppState:
    """Функция сохраняет состояние программы из сессии session в состояние state.

    Parameters
    ----------
    state : AppState
        Переменная, в которую будет записано состояние программы.
    _session: streamlit.session_state
        Сессия приложения, из которой будет извлекаться состояние программы.
    Returns
    -------
    """
    state['adapt_params'] = {}
    state['buffer'] = None
    state['ensemble_interval'] = pd.DataFrame()
    state['exclude_wells'] = []
    state['statistics'] = {}
    state['statistics_test_only'] = {}
    state['selected_wells_norm'] = selected_wells_norm.copy()
    state['selected_wells_ois'] = selected_wells_ois.copy()
    state['was_config'] = config
    state['was_calc_ftor'] = models['ftor']
    state['was_calc_wolfram'] = models['wolfram']
    state['was_calc_CRM'] = models['CRM']
    state['was_calc_ensemble'] = models['ensemble']
    state['was_date_start'] = date_start
    state['was_date_test'] = date_test
    state['was_date_test_if_ensemble'] = date_test + timedelta(days=_session.ensemble_adapt_period)
    state['was_date_end'] = date_end
    state['wellnames_key_normal'] = wellnames_key_normal.copy()
    state['wellnames_key_ois'] = wellnames_key_ois.copy()
    state['wells_ftor'] = preprocessor.create_wells_ftor(selected_wells_ois)
    return state


def select_page(pages: Dict[str, Any]) -> str:
    """Виджет выбора страницы (вкладки) в интерфейсе.
    """
    _selected_page = st.radio("", list(pages.keys()))
    return _selected_page


def select_models() -> Dict[str, bool]:
    """Виджет выбора моделей для расчета.
    """
    selected_models = {
        'ftor': st.checkbox(
            label='Считать модель пьезопр-ти',
            value=True,
            key='is_calc_ftor',
        ),
        'wolfram': st.checkbox(
            label='Считать модель ML',
            value=True,
            key='is_calc_wolfram',
        ),
        'CRM': st.checkbox(
            label='Считать модель CRM',
            value=True,
            key='is_calc_CRM',
        ),
        'ensemble': st.checkbox(
            label='Считать ансамбль моделей',
            value=True,
            key='is_calc_ensemble',
            help='Ансамбль возможно рассчитать, если рассчитана хотя бы одна модель.'
        ),
    }
    return selected_models


def select_oilfield(fields_shops: Dict[str, List[str]]) -> str:
    """Виджет выбора месторождения для расчета.

    Parameters
    ----------
    fields_shops : Dict[str, List[str]]
        цеха для каждого месторождения
    """
    oilfield_name = st.selectbox(
        label='Месторождение',
        options=fields_shops.keys(),
        key='field_name',
    )
    return oilfield_name


def select_dates(date_min: date,
                 date_max: date) -> Tuple[date, date, date]:
    """Виджет выбора дат адаптации и прогноза.
    """
    date_start_ = st.date_input(
        label='Дата начала адаптации (с 00:00)',
        min_value=date_min,
        value=date(2018, 12, 1),
        max_value=date_max,
        key='date_start',
        help="""
        Данная дата используется только для модели пьезопроводности.
        Адаптация модели ML проводится на всех доступных по скважине данных.
        """,
    )
    date_test_ = st.date_input(
        label='Дата начала прогноза (с 00:00)',
        min_value=date_min,
        value=date(2019, 3, 1),
        max_value=date_max,
        key='date_test',
    )
    date_end_ = st.date_input(
        label='Дата конца прогноза (по 23:59)',
        min_value=date_min,
        value=date(2019, 5, 30),
        max_value=date_max,
        key='date_end',
    )
    return date_start_, date_test_, date_end_


def select_wells_to_calc(wellnames_key_normal_: Dict[str, int]) -> Tuple[List[str], List[int]]:
    """Виджет выбора скважин для расчета.
    """
    wells_norm = st.multiselect(label='Скважина',
                                options=['Все скважины'] + list(wellnames_key_normal_.keys()),
                                key='selected_wells_norm')
    if 'Все скважины' in wells_norm:
        wells_norm = list(wellnames_key_normal_.keys())
    wells_ois = [wellnames_key_normal_[well_name_] for well_name_ in wells_norm]
    return wells_norm, wells_ois


def check_for_correct_params(date_start_: date,
                             date_test_: date,
                             date_end_: date,
                             pressed_submit: bool,
                             selected_wells_norm_: List[str]) -> None:
    """Проверяет корректность параметров, выбранных пользователем.

    - Даты адаптации
    - Даты прогноза
    - Выбрана ли хоть одна скважина для расчета
    """
    adaptation_days_number = (date_test_ - date_start_).days
    forecast_days_number = (date_end_ - date_test_).days
    if adaptation_days_number < 90 or forecast_days_number < 28:
        st.error('**Период адаптации** должен быть не менее 90 суток. **Период прогноза** - не менее 28 суток.')
    if pressed_submit and not selected_wells_norm_:
        st.info('Не выбрано ни одной скважины для расчета.')


def run_models(_session: st.session_state,
               _models: Dict[str, bool],
               _preprocessor: Preprocessor,
               wells_ois: List[int],
               wells_norm: List[str],
               date_start_adapt: date,
               date_start_forecast: date,
               date_end_forecast: date,
               oilfield: str) -> None:
    """Запуск расчета моделей, которые выбрал пользователь.

    Parameters
    ----------
    _session : st.session_state
        текущая сессия streamlit. В ней содержатся настройки моделей и
        текущее состояние программы _session.state.
    _models : Dict[str, bool]
        модели для расчета, которые выбрал пользователь.
    _preprocessor : Preprocessor
        препроцессор с конфигурацией, заданной пользователем.
    wells_ois : List[int]
        список имен скважин в формате OIS.
    wells_norm : List[str]
        список имен скважин в "читаемом" формате (ГРАД?).
    date_start_adapt : date
        дата начала адаптации для модели пьезопроводности.
    date_start_forecast : date
        дата начала прогноза для всех моделей, кроме ансамбля.
    date_end_forecast : date
        дата конца прогноза для всех моделей.
    oilfield : str
        название месторождения, которое выбрал пользователь.

    Notes
    -------
    В конце расчета каждой из моделей вызывается функция извлечения результатов.
    Таким образом все результаты приводятся к единому формату данных.
    """
    at_least_one_model = _models['ftor'] or _models['wolfram'] or _models['CRM']
    if _models['ftor']:
        calculator_ftor = calculate_ftor(_preprocessor, wells_ois, _session.constraints)
        extract_data_ftor(calculator_ftor, _session.state)
    if _models['wolfram']:
        forecast_days_number = (date_end_forecast - date_start_forecast).days
        calculator_wolfram = calculate_wolfram(_preprocessor,
                                               wells_ois,
                                               forecast_days_number,
                                               _session.estimator_name_group,
                                               _session.estimator_name_well,
                                               _session.is_deep_grid_search,
                                               _session.window_sizes,
                                               _session.quantiles)
        extract_data_wolfram(calculator_wolfram, _session.state)
        convert_tones_to_m3_for_wolfram(_session.state, _session.state.wells_ftor)
    if _models['CRM']:
        calculator_CRM = calculate_CRM(date_start_adapt=date_start_adapt,
                                       date_end_adapt=date_start_forecast - timedelta(days=1),
                                       date_end_forecast=date_end_forecast,
                                       oilfield=oilfield)
        CRM = calculator_CRM.CRM
        pred_CRM = calculator_CRM.pred_CRM
        extract_data_CRM(pred_CRM, _session.state, _session.state['wells_ftor'], mode='CRM')
    if at_least_one_model:
        make_models_stop_well(_session.state['statistics'], _session.state['selected_wells_norm'])
    if at_least_one_model and _models['ensemble']:
        name_of_y_true = 'true'
        for ind, well_name_normal in enumerate(wells_norm):
            print(f'\nWell {ind + 1} out of {len(wells_norm)}\n')
            input_df = prepare_df_for_ensemble(_session.state, well_name_normal, name_of_y_true)
            ensemble_result = calculate_ensemble(
                input_df,
                adaptation_days_number=_session.ensemble_adapt_period,
                interval_probability=_session.interval_probability,
                draws=_session.draws,
                tune=_session.tune,
                chains=_session.chains,
                target_accept=_session.target_accept,
                name_of_y_true=name_of_y_true
            )
            if not ensemble_result.empty:
                extract_data_ensemble(ensemble_result, _session.state, well_name_normal)


PAGES = {
    "Настройки моделей": UI.pages.models_settings,
    "Карта скважин": UI.pages.wells_map,
    "Аналитика": UI.pages.analytics,
    "Скважина": UI.pages.specific_well,
    "Импорт/экспорт расчетов": UI.pages.resume_app,
}

if __name__ == '__main__':
    session = start_streamlit()
    # Реализация UI: сайдбар
    with st.sidebar:
        selected_page = select_page(PAGES)
        models = select_models()
        field_name = select_oilfield(FIELDS_SHOPS)
        date_start, date_test, date_end = select_dates(date_min=DATE_MIN, date_max=DATE_MAX)

        config = ConfigPreprocessor(field_name, FIELDS_SHOPS[field_name], date_start, date_test, date_end)
        preprocessor = run_preprocessor(config)
        wellnames_key_normal, wellnames_key_ois = parse_well_names(preprocessor.well_names)
        selected_wells_norm, selected_wells_ois = select_wells_to_calc(wellnames_key_normal)

        submit = st.button(label='Запустить расчеты')
    check_for_correct_params(date_start, date_test, date_end, submit, selected_wells_norm)
    # Отображение выбранной страницы
    page = PAGES[selected_page]
    page.show(session)

    # Нажата кнопка "Запуск расчетов"
    if submit and selected_wells_norm:
        session.state = get_current_state(AppState(), session)
        # Запуск моделей
        run_models(session, models, preprocessor,
                   selected_wells_ois, selected_wells_norm,
                   date_start, date_test, date_end, field_name)
        # Выделение прогнозов моделей
        dfs, dates = cut_statistics_test_only(session.state)
        session.state.statistics_test_only, session.state.statistics_test_index = dfs, dates
