import json
from typing import Any, Dict
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st


st.set_page_config(page_title='KZFR Show Getter', page_icon='📻')


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


@st.cache(persist=True, ttl=(60 * 15))  # refresh every ``15`` minutes
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
    show_titles = [x['title'] for x in shows_dict['data']]

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
        archives_df[col] = pd.to_datetime(archives_df[col], utc=True).dt.tz_convert('US/Pacific')

    archives_df['start_readable'] = archives_df['start'].dt.strftime('%m/%d/%Y @ %I:%M %p')

    return show_titles, archives_df


show_titles, archives_df = read_studio_creek_website_data()


show_options = ['-'] + show_titles

if not show_options:
    st.error('No KZFR shows found in the current Studio Creek archive.')
    st.stop()

st.experimental_set_query_params()
query_params = st.experimental_get_query_params()

try:
    query_params_show_selected = query_params['show_selected'][0]
    show_selected_idx = show_options.index(query_params_show_selected)
except (IndexError, KeyError, ValueError):
    show_selected_idx = 0

show_selected = st.selectbox(
    label='Select a show name to view',
    options=show_options,
    index=show_selected_idx,
)

if show_selected and show_selected != '-':
    filtered_df = archives_df[archives_df['title'] == show_selected]

    if len(filtered_df) == 0:
        st.error(f'No "{show_selected}" shows found in the current Studio Creek archive.')
        st.stop()

    time_options = ['-'] + filtered_df['start_readable'].unique().tolist()

    if not time_options:
        st.error(f'No "{show_selected}" show times found in the current Studio Creek archive.')
        st.stop()

    try:
        query_params_time_selected = query_params['time_selected'][0]
        time_selected_idx = time_options.index(query_params_time_selected)
    except (IndexError, KeyError, ValueError):
        time_selected_idx = 0

    time_selected = st.selectbox(
        label='Select a show time to view',
        options=time_options,
        index=time_selected_idx,
    )

    if time_selected and time_selected != '-':
        # weird note: this has to include what we already set above ¯\_(ツ)_/¯
        st.experimental_set_query_params(show_selected=show_selected, time_selected=time_selected)

        # select the first show with the matching time
        show_series = filtered_df[filtered_df['start_readable'] == time_selected].iloc[0]

        st.markdown(f'## {show_series.get("title")}')

        st.image(image=show_series['image_url'])

        if show_series.get('summary'):
            st.markdown(body=f'**Show Summary**: {show_series["summary"]}', unsafe_allow_html=True)

        if show_series.get('description'):
            st.markdown(
                body=f'**Show Description**: {show_series["description"]}',
                unsafe_allow_html=True,
            )

        st.markdown('<br>', unsafe_allow_html=True)

        if show_series.get('url'):
            st.markdown('**Episode Audio Stream**:')
            st.audio(data=show_series['url'])
            st.markdown(f'... or download the audio from the URL here: {show_series["url"]}')
