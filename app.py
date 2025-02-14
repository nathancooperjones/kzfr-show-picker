from datetime import datetime
import json
import re
from typing import Any, Dict, Optional, Union
from urllib.request import Request, urlopen

from hurry.filesize import size
import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title='KZFR Show Picker',
    page_icon='📻',
    initial_sidebar_state='collapsed',
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

# hide Streamlit style and center all images with custom CSS
st.html(
    body="""
        <style>
            div[data-testid="stImage"] {
                display: block;
                margin-left: auto;
                margin-right: auto;
            }

             /* so hacky omg but it works for now so whatever */
            div[data-testid="stFullScreenFrame"] > div {
                text-align: center;
                display: block;
                margin-left: auto;
                margin-right: auto;
                width: 100%;
            }
        </style>
    """,
)


st.image(
    image='https://www.kzfr.org/theme/51/images/header/KZFR_Logo_Color_isolated_full_szie.png',
    width=250,
)
st.markdown(body='# KZFR Show Picker')


def make_request(url: str) -> Dict[str, Any]:
    """Make a request to a url ``url`` with proper headings, returning the JSON-ified response."""
    with urlopen(url=Request(url=url, headers={'User-Agent': 'Mozilla/5.0'})) as fp:
        response_dict = json.load(fp=fp)

    return response_dict


@st.cache_data(show_spinner=False, ttl=(60 * 15))  # refresh every ``15`` minutes
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
        archives_df = pd.DataFrame(
            data=[
                {
                    'id': item['id'],
                    'start': item['start'],
                    'end': item['end'],
                    'title': item['show']['title'],
                    'name': item['show']['name'],
                    'summary': item['show']['summary'],
                    'description': item['show']['description'],
                    # 'image_url': item['image']['url'],
                    'image_url': (item.get('image') or {}).get('url'),
                    'filesize': item['audio']['filesize'],
                    'url': item['audio']['url'],
                }
                for item in archives_dict_data
            ]
        )
        archives_df['start'] = (
            pd.to_datetime(arg=archives_df['start'], utc=True).dt.tz_convert(tz='US/Pacific')
        )
        archives_df['end'] = (
            pd.to_datetime(arg=archives_df['end'], utc=True).dt.tz_convert(tz='US/Pacific')
        )
        archives_df['start_readable'] = (
            archives_df['start'].dt.strftime(date_format='%m/%d/%Y @ %I:%M %p')
        )

        return show_titles, archives_df


def check_if_url_exists(url: str) -> bool:
    """Check if a URL exists or not."""
    try:
        return requests.head(url=url).status_code == 200
    except requests.RequestException:
        return False


def display_audio_stream(url: str, filesize: Optional[int] = None) -> None:
    """Write the markdown needed to display the audio stream at url ``url``."""
    st.markdown(body='**Episode Audio Stream**:')
    st.audio(data=url)

    if filesize:
        st.markdown(body=f'... or download the audio from the URL here ({size(filesize)}): {url}')
    else:
        st.markdown(body=f'... or download the audio from the URL here: {url}')


def display_stream_with_metadata(
    title: str,
    time_selected: Union[str, datetime],
    image_url: Optional[str] = None,
    summary: Optional[str] = None,
    description: Optional[str] = None,
    url: Optional[str] = None,
    filesize: Optional[str] = None,
) -> None:
    """Render the markdown to display any provided show's metadata followed by the stream audio."""
    st.markdown(body=f'## {title}')
    st.markdown(body=f'##### {time_selected}')

    if image_url:
        st.image(image=image_url, width=350)

    if summary:
        st.markdown(
            body=f'**Show Summary**: {summary}',
            unsafe_allow_html=True,
        )

    if description:
        st.markdown(
            body=f'**Show Description**: {description}',
            unsafe_allow_html=True,
        )

    st.markdown(body='<br>', unsafe_allow_html=True)

    if url:
        display_audio_stream(url=url, filesize=filesize)


show_titles, archives_df = read_studio_creek_website_data()


SHOW_TIME_SELECTION_OPTIONS = [
    'Search for a show in the archive',
    'Search for a show NOT in the archive',
]


show_options = show_titles

if len(show_options) <= 1:
    st.error('No KZFR shows found in the current Studio Creek archive.')
    st.stop()

query_params = {}
st.first_time_running = False

if len(st.session_state) == 0:
    query_params = st.query_params.to_dict()

    # ugh... Streamlit workarounds I guess
    if len(query_params) == 2:
        st.first_time_running = True

if not st.session_state.get('show_selected'):
    try:
        query_params_show_selected = query_params['show_selected']
        show_selected_idx = show_options.index(query_params_show_selected)
    except (IndexError, KeyError, ValueError):
        show_selected_idx = None

st.selectbox(
    label='Select a KZFR show name',
    options=show_options,
    index=show_selected_idx if 'show_selected_idx' in locals() else None,
    key='show_selected',
)

st.query_params.clear()

if st.session_state.show_selected:
    st.query_params.clear()

    filtered_df = archives_df[archives_df['title'] == st.session_state.show_selected]
    time_options = filtered_df['start_readable'].unique().tolist()

    if not st.session_state.get('show_time_selection'):
        try:
            query_params_show_time_selection = query_params['time_selected']
            query_params_show_time_selection_idx = 1
        except (IndexError, KeyError, ValueError):
            query_params_show_time_selection_idx = 0

    if st.first_time_running and 'query_params_show_time_selection_idx' in locals():
        st.session_state.show_time_selection = (
            SHOW_TIME_SELECTION_OPTIONS[query_params_show_time_selection_idx]
        )
    else:
        st.radio(
            label=f'How would you like to find the show time for {st.session_state.show_selected}?',
            options=SHOW_TIME_SELECTION_OPTIONS,
            **(
                {'index': query_params_show_time_selection_idx}
                if 'query_params_show_time_selection_idx' in locals()
                else {}
            ),
            key='show_time_selection',
        )

    if st.session_state.show_time_selection == SHOW_TIME_SELECTION_OPTIONS[0]:
        if not time_options:
            st.error(
                f'No "{st.session_state.show_selected}" show times found in the current Studio '
                'Creek archive.'
            )
            st.stop()
        else:
            st.selectbox(
                label=f'Select a {st.session_state.show_selected} show date',
                options=time_options,
                key='time_selected',
            )

            if st.session_state.time_selected:
                # weird note: this has to include what we already set above ¯\_(ツ)_/¯
                st.query_params.from_dict(
                    params={
                        'show_selected': st.session_state.show_selected,
                        'time_selected': st.session_state.time_selected,
                    },
                )

                # select the first show with the matching time
                try:
                    show_series = (
                        filtered_df[
                            filtered_df['start'].dt.strftime('%Y-%m-%d_%H-%M-%S')
                            == st.session_state.time_selected
                        ]
                        .iloc[0]
                    )
                except IndexError:
                    try:
                        show_series = (
                            filtered_df[
                                filtered_df['start_readable'] == st.session_state.time_selected
                            ]
                            .iloc[0]
                        )
                    except IndexError:
                        st.error(
                            'No show found at the date and time '
                            f'`{st.session_state.time_selected}`. Please try again with new '
                            'options.'
                        )
                        st.stop()

                if check_if_url_exists(url=show_series.get('url')):
                    display_stream_with_metadata(
                        title=show_series.get('title'),
                        time_selected=st.session_state.time_selected,
                        image_url=show_series.get('image_url'),
                        summary=show_series.get('summary'),
                        description=show_series.get('description'),
                        url=show_series.get('url'),
                        filesize=show_series.get('filesize'),
                    )
                else:
                    st.error(
                        f'No show found at the date and time `{st.session_state.time_selected}`. '
                        'Please try again with new options.'
                    )
                    st.stop()

    elif st.session_state.show_time_selection == SHOW_TIME_SELECTION_OPTIONS[1]:
        normalized_show_name = (
            re.sub(r'[^\w\s]', '', st.session_state.show_selected)
            .replace('  ', ' ')
            .replace(' ', '-')
            .lower()
        )

        if not st.session_state.get('time_selected'):
            try:
                query_params_time_selected = query_params['time_selected']

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

        filtered_df = archives_df[archives_df['title'] == st.session_state.show_selected]

        image_url = None
        summary = None
        description = None

        if len(filtered_df) > 0:
            filtered_df_row = filtered_df.iloc[0]

            image_url = filtered_df_row['image_url']
            summary = filtered_df_row['summary']
            description = filtered_df_row['description']

        if st.first_time_running and 'query_params_time_selected' in locals():
            st.session_state.time_selected = (
                query_params_time_selected_datetime.strftime('%Y-%m-%d_%H-%M-%S')
            )
        else:
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

            st.caption(
                "Note that shows aired earlier than ``8/8/22`` MAY NOT appear in Studio Creek's "
                'database.'
            )

            st.session_state.time_selected = (
                f'{show_date.strftime("%Y-%m-%d")}_{show_time.strftime("%H-%M-%S")}'
            )

        # weird note: this has to include what we already set above ¯\_(ツ)_/¯
        st.query_params.from_dict(
            params={
                'show_selected': st.session_state.show_selected,
                'time_selected': st.session_state.time_selected,
            },
        )

        # ugh what a stupid hack
        philosophers_on_culture_and_whats_the_frequency_kenneth_time_swap_dict = {
            '2023-11-09_17-00-00': '2023-11-16_17-00-00',
            '2023-10-26_17-00-00': '2023-11-02_17-00-00',
            '2023-10-12_17-00-00': '2023-10_19-17-00-00',
            '2023-09-28_17-00-00': '2023-10_05-17-00-00',
            '2023-09-14_17-00-00': '2023-09_21-17-00-00',
            '2023-08-31_17-00-00': '2023-09_07-17-00-00',
            '2023-08-17_17-00-00': '2023-08-24_17-00-00',
            '2023-08-03_17-00-00': '2023-08-10_17-00-00',
            '2023-07-20_17-00-00': '2023-07-27_17-00-00',
        }
        whats_the_frequency_kenneth_time_swap_and_philosophers_on_culture_dict = {
            v: k
            for k, v in (
                philosophers_on_culture_and_whats_the_frequency_kenneth_time_swap_dict.items()
            )
        }
        time_swap_dict = {
            **philosophers_on_culture_and_whats_the_frequency_kenneth_time_swap_dict,
            **whats_the_frequency_kenneth_time_swap_and_philosophers_on_culture_dict
        }

        if st.session_state.time_selected in time_swap_dict:
            st.session_state.time_selected = time_swap_dict[st.session_state.time_selected]
            normalized_show_name = (
                'whats-the-frequency-kenneth'
                if normalized_show_name == 'philosophers-on-culture'
                else 'philosophers-on-culture'
            )

        url = (
            'https://kzfr-media.s3.us-west-000.backblazeb2.com/audio/'
            f'{normalized_show_name}/{normalized_show_name}_{st.session_state.time_selected}.mp3'
        )

        time_selected_to_display = (
            datetime.strptime(st.session_state.time_selected, '%Y-%m-%d_%H-%M-%S')
            .strftime('%m/%d/%Y @ %I:%M %p')
        )

        filesize_df = archives_df[archives_df['url'] == url]

        filesize = None

        if len(filesize_df) > 0:
            filesize = filesize_df['filesize'].iloc[0]

        if check_if_url_exists(url=url):
            display_stream_with_metadata(
                title=st.session_state.show_selected,
                time_selected=time_selected_to_display,
                image_url=image_url,
                summary=summary,
                description=description,
                url=url,
                filesize=filesize,
            )
        else:
            st.error(
                f'No show found at the date and time `{st.session_state.time_selected}`. '
                'Please try again with new options.'
            )
            st.stop()

st.markdown(body='-----')

st.caption(
    'Find more about KZFR and their shows on their official website: '
    '[kzfr.org](http://www.kzfr.org)!'
)

if st.first_time_running:
    # this just re-runs the app
    st.markdown(body='<br>', unsafe_allow_html=True)
    st.markdown(body='<br>', unsafe_allow_html=True)
    st.markdown(body='<br>', unsafe_allow_html=True)
    st.button('Reset search')
