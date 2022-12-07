from datetime import datetime
import json
import re
from typing import Any, Dict
from urllib.request import Request, urlopen

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title='KZFR Show Getter',
    page_icon='📻',
    menu_items={
        'Get help': None,
        'Report a Bug': 'https://github.com/nathancooperjones/kzfr-show-picker/issues',
        'About': (
            'An alternative to the Studio Creek KZFR archive found here: '
            'https://kzfr.studio.creek.org/archives/. In comparison, this website lets you find '
            'show archives that might not be visible in the archive AND create a static URL that '
            'you can share out with others that leads directly to the show you find - beautiful!'
        ),
    }
)


hide_streamlit_style = """
    <style>
    div[data-testid="stImage"] {
        display: block;
        margin-left: auto;
        margin-right: auto;
    }
    </style>
"""

st.markdown(hide_streamlit_style, unsafe_allow_html=True)


st.image(
    image='https://www.kzfr.org/theme/51/images/header/KZFR_Logo_Color_isolated_full_szie.png',
    width=250,
)
st.markdown('# KZFR Show Picker')


def make_request(url: str) -> Dict[str, Any]:
    """Make a request to a url ``url`` with proper headings, returning the JSON-ified response."""
    headers = {'User-Agent': 'Mozilla/5.0'}
    request = Request(url=url, headers=headers)

    with urlopen(url=request) as fp:
        response_dict = json.load(fp=fp)

    return response_dict


@st.cache(persist=True, show_spinner=False, ttl=(60 * 15))  # refresh every ``15`` minutes
def read_studio_creek_website_data() -> pd.DataFrame:
    """
    Parse the Studio Creek APIs for both show names and archives.

    This is cached using ``st.cache`` and configured to reset every 15 minutes.

    Returns
    -------
    show_titles: list
        A list of all shows returned in the ``shows-list`` API endpoint
    archives_df: pd.DataFrame
        A DataFrame containing the show archives data, specifically columns:

            * id: str

            * start: datetime

            * end: datetime

            * title: str

            * name: str

            * summary: str

            * description: str

            * image_url: str

            * filesize: int

            * url: str

    """
    with st.spinner(text='Refreshing our show list with the Studio Creek archives...'):
        shows_dict = make_request(url='https://kzfr.studio.creek.org/api/archives/shows-list')

        archives_dict_data = list()
        archives_page = 1

        while True:
            archives_dict = make_request(
                url=f'https://kzfr.studio.creek.org/api/archives?page={archives_page}',
            )
            archives_dict_data += archives_dict['data']

            if archives_dict['links'].get('next'):
                archives_page += 1
            else:
                break

        # prep show titles
        show_titles = sorted(set([x['title'] for x in shows_dict['data']]))

        # prep archives data
        archives_dict_data_subset = [
            {
                'id': data['id'],
                'start': data['start'],
                'end': data['end'],
                'title': data['show']['title'],
                'name': data['show']['name'],
                'summary': data['show']['summary'],
                'description': data['show']['description'],
                'image_url': data['image']['url'],
                'filesize': data['audio']['filesize'],
                'url': data['audio']['url'],
            }
            for data in archives_dict_data
        ]

        archives_df = pd.DataFrame(data=archives_dict_data_subset)

        for col in ['start', 'end']:
            archives_df[col] = (
                pd
                .to_datetime(archives_df[col], utc=True)
                .dt
                .tz_convert('US/Pacific')
            )

        archives_df['start_readable'] = archives_df['start'].dt.strftime('%m/%d/%Y @ %I:%M %p')

        return show_titles, archives_df


def check_if_url_exists(url: str) -> bool:
    """Check if a URL exists or not."""
    try:
        response = requests.head(url)

        return response.status_code == 200
    except requests.ConnectionError:
        return False


def display_audio_stream(url: str) -> None:
    """Write the markdown needed to display the audio stream at url ``url``."""
    st.markdown('**Episode Audio Stream**:')
    st.audio(data=url)
    st.markdown(f'... or download the audio from the URL here: {url}')


show_titles, archives_df = read_studio_creek_website_data()


SHOW_TIME_SELECTION_OPTIONS = [
    'Search for a show in the archive',
    'Search for a show NOT in the archive',
]


show_options = ['-'] + show_titles

if len(show_options) <= 1:
    st.error('No KZFR shows found in the current Studio Creek archive.')
    st.stop()

query_params = {}
st.first_time_running = False

if len(st.session_state) == 0:
    query_params = st.experimental_get_query_params()

    # ugh... Streamlit workarounds I guess
    if len(query_params) == 2:
        st.first_time_running = True

if not st.session_state.get('show_selected'):
    try:
        query_params_show_selected = query_params['show_selected'][0]
        show_selected_idx = show_options.index(query_params_show_selected)
    except (IndexError, KeyError, ValueError):
        show_selected_idx = 0

if st.first_time_running and 'show_selected_idx' in locals():
    st.session_state.show_selected = show_options[show_selected_idx]
else:
    st.session_state.show_selected = st.selectbox(
        label='Select a KZFR show name',
        options=show_options,
        **({'index': show_selected_idx} if 'show_selected_idx' in locals() else {}),
    )

st.experimental_set_query_params()

if st.session_state.show_selected and st.session_state.show_selected != '-':
    st.experimental_set_query_params()

    filtered_df = archives_df[archives_df['title'] == st.session_state.show_selected]
    time_options = filtered_df['start_readable'].unique().tolist()

    if not st.session_state.get('show_time_selection'):
        try:
            query_params_show_time_selection = query_params['time_selected'][0]
            query_params_show_time_selection_idx = 1
        except (IndexError, KeyError, ValueError):
            query_params_show_time_selection_idx = 0

    if st.first_time_running and 'query_params_show_time_selection_idx' in locals():
        st.session_state.show_time_selection = (
            SHOW_TIME_SELECTION_OPTIONS[query_params_show_time_selection_idx]
        )
    else:
        st.session_state.show_time_selection = st.radio(
            label='How would you like to find the show time?',
            options=SHOW_TIME_SELECTION_OPTIONS,
            **(
                {'index': query_params_show_time_selection_idx}
                if 'query_params_show_time_selection_idx' in locals()
                else {}
            ),
        )

    if st.session_state.show_time_selection == SHOW_TIME_SELECTION_OPTIONS[0]:
        if not time_options:
            st.error(
                f'No "{st.session_state.show_selected}" show times found in the current Studio '
                'Creek archive.'
            )
        else:
            st.session_state.time_selected = st.selectbox(
                label=f'Select a {st.session_state.show_selected} show date',
                options=time_options,
            )

            if st.session_state.time_selected and st.session_state.time_selected != '-':
                # weird note: this has to include what we already set above ¯\_(ツ)_/¯
                st.experimental_set_query_params(
                    show_selected=st.session_state.show_selected,
                    time_selected=st.session_state.time_selected,
                )

                # select the first show with the matching time
                show_series = (
                    filtered_df[
                        filtered_df['start_readable'] == st.session_state.time_selected
                    ]
                    .iloc[0]
                )

                st.markdown(f'## {show_series.get("title")}')
                st.markdown(f'##### {st.session_state.time_selected}')

                st.image(image=show_series['image_url'])

                if show_series.get('summary'):
                    st.markdown(
                        body=f'**Show Summary**: {show_series["summary"]}',
                        unsafe_allow_html=True,
                    )

                if show_series.get('description'):
                    st.markdown(
                        body=f'**Show Description**: {show_series["description"]}',
                        unsafe_allow_html=True,
                    )

                st.markdown('<br>', unsafe_allow_html=True)

                if show_series.get('url'):
                    display_audio_stream(url=show_series['url'])
    else:
        normalized_show_name = (
            re.sub(r'[^\w\s]', '', st.session_state.show_selected)
            .replace(' ', '-')
            .lower()
        )

        if not st.session_state.get('time_selected'):
            try:
                query_params_time_selected = query_params['time_selected'][0]

                try:
                    # show time selection option 2
                    query_params_time_selected_datetime = datetime.strptime(
                        query_params_time_selected,
                        '%Y-%m-%d_%H-%M-%S',
                    )
                except ValueError:
                    # show time selection option 1
                    query_params_time_selected_datetime = datetime.strptime(
                        query_params_time_selected,
                        '%m/%d/%Y @ %I:%M %p',
                    )
            except (IndexError, KeyError, ValueError):
                query_params_time_selected_datetime = None

        col_1, col_2 = st.columns(spec=2)

        if st.first_time_running and 'query_params_time_selected' in locals():
            st.session_state.time_selected = (
                query_params_time_selected_datetime.strftime('%Y-%m-%d_%H-%M-%S')
            )
        else:
            filtered_df = archives_df[archives_df['title'] == st.session_state.show_selected]

            if len(filtered_df) > 0:
                try:
                    first_found_show_time = filtered_df['start'].iloc[0]

                    if 'query_params_time_selected_datetime' not in locals():
                        query_params_time_selected_datetime = first_found_show_time
                except IndexError:
                    pass

            with col_1:
                show_date = st.date_input(
                    label='What day did the show occur?',
                    **(
                        {'value': query_params_time_selected_datetime}
                        if 'query_params_time_selected_datetime' in locals()
                        else {}
                    ),
                )
            with col_2:
                show_time = st.time_input(
                    label='What time (24-hour time in PST) did the show occur?',
                    **(
                        {'value': query_params_time_selected_datetime}
                        if 'query_params_time_selected_datetime' in locals()
                        else {}
                    ),
                )

            st.session_state.time_selected = (
                f'{show_date.strftime("%Y-%m-%d")}_{show_time.strftime("%H-%M-%S")}'
            )

        # weird note: this has to include what we already set above ¯\_(ツ)_/¯
        st.experimental_set_query_params(
            show_selected=st.session_state.show_selected,
            time_selected=st.session_state.time_selected,
        )

        url = (
            'https://kzfr-media.s3.us-west-000.backblazeb2.com/audio/'
            f'{normalized_show_name}/{normalized_show_name}_{st.session_state.time_selected}.mp3'
        )

        if check_if_url_exists(url=url):
            # to be consistent
            time_selected_to_display = (
                datetime.strptime(st.session_state.time_selected, '%Y-%m-%d_%H-%M-%S')
                .strftime('%m/%d/%Y @ %I:%M %p')
            )

            st.markdown(f'## {st.session_state.show_selected}')
            st.markdown(f'##### {time_selected_to_display}')
            display_audio_stream(url=url)
        else:
            st.error(
                f'No show found at the date and time {st.session_state.time_selected}. Please try '
                'again with new options.'
            )

if st.first_time_running:
    # this just re-runs the app
    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown('<br>', unsafe_allow_html=True)
    st.markdown('<br>', unsafe_allow_html=True)
    st.button('Reset search')
