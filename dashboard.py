import streamlit as st
import pandas as pd
import pymongo
from pymongo import MongoClient
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
import base64

# Page configuration
st.set_page_config(
    page_title="Streamer Analytics Dashboard",
    page_icon="🎮",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e3a8a;
        text-align: center;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8fafc;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #3b82f6;
    }
    .stDataFrame {
        border: 1px solid #e5e7eb;
        border-radius: 0.5rem;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_data_from_mongodb():
    """Load data from MongoDB with caching using secrets"""
    try:
        # Read MongoDB configuration from secrets
        mongo_uri = st.secrets["mongodb"]["uri"]
        db_name = st.secrets["mongodb"]["database"]
        collection_name = st.secrets["mongodb"]["collection"]
        
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db = client[db_name]
        collection = db[collection_name]
        
        # Fetch all documents
        documents = list(collection.find({}))
        client.close()
        
        if documents:
            df = pd.DataFrame(documents)
            # Remove MongoDB _id field if present
            if '_id' in df.columns:
                df = df.drop('_id', axis=1)
            return df, db_name, collection_name
        else:
            return pd.DataFrame(), db_name, collection_name
            
    except KeyError as e:
        st.error(f"Missing configuration in secrets.toml: {e}")
        st.info("Please ensure your .streamlit/secrets.toml file contains the MongoDB configuration.")
        return pd.DataFrame(), "", ""
    except Exception as e:
        st.error(f"Error connecting to MongoDB: {e}")
        return pd.DataFrame(), "", ""

def create_download_link(df, filename, file_format):
    """Create download link for dataframe"""
    if file_format == "CSV":
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv">📥 Download CSV</a>'
    elif file_format == "Excel":
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Streamers')
        output.seek(0)
        b64 = base64.b64encode(output.read()).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">📥 Download Excel</a>'
    
    return href

def apply_filters(df, filters):
    """Apply filters to dataframe"""
    filtered_df = df.copy()
    
    # Text search
    if filters['search_term']:
        search_columns = ['username', 'game_name', 'language', 'twitter']
        mask = False
        for col in search_columns:
            if col in filtered_df.columns:
                mask |= filtered_df[col].astype(str).str.contains(filters['search_term'], case=False, na=False)
        filtered_df = filtered_df[mask]
    
    # Status filter
    if filters['status_filter'] != "All":
        filtered_df = filtered_df[filtered_df['is_live'] == filters['status_filter']]
    
    # Verification filter
    if filters['verification_filter'] != "All":
        filtered_df = filtered_df[filtered_df['isVerified'] == filters['verification_filter']]
    
    # Viewer count range
    if 'viewer_range' in filters and 'current_viewers' in filtered_df.columns:
        filtered_df = filtered_df[
            (filtered_df['current_viewers'] >= filters['viewer_range'][0]) &
            (filtered_df['current_viewers'] <= filters['viewer_range'][1])
        ]
    
    # Streaming time range
    if 'streaming_time_range' in filters and 'total_streaming_minutes' in filtered_df.columns:
        filtered_df = filtered_df[
            (filtered_df['total_streaming_minutes'] >= filters['streaming_time_range'][0]) &
            (filtered_df['total_streaming_minutes'] <= filters['streaming_time_range'][1])
        ]
    
    return filtered_df

def safe_slider(label, column_data, key_suffix=""):
    """Create a slider with safe min/max values"""
    if column_data.isna().all():
        st.sidebar.info(f"{label}: No data available")
        return None
    
    min_val = float(column_data.min())
    max_val = float(column_data.max())
    
    # Handle case where all values are the same
    if min_val == max_val:
        st.sidebar.info(f"{label}: All values are {min_val}")
        return (min_val, max_val)
    
    # Ensure min is less than max
    if min_val >= max_val:
        st.sidebar.info(f"{label}: Invalid range (min: {min_val}, max: {max_val})")
        return None
    
    return st.sidebar.slider(
        label, 
        min_value=min_val, 
        max_value=max_val, 
        value=(min_val, max_val),
        key=f"slider_{key_suffix}"
    )

def main():
    # Header
    st.markdown('<h1 class="main-header">🎮 Streamer Analytics Dashboard</h1>', unsafe_allow_html=True)
    
    # Sidebar configuration
    st.sidebar.header("⚙️ Configuration")
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data", type="primary"):
        st.cache_data.clear()
        st.rerun()
    
    # Load data
    with st.spinner("Loading data from MongoDB..."):
        df, db_name, collection_name = load_data_from_mongodb()
    
    if df.empty:
        st.warning("No data found. Please check your MongoDB connection and collection.")
        st.info("Make sure your `.streamlit/secrets.toml` file is properly configured.")
        return
    
    # Convert numeric columns to proper types
    numeric_columns = ['current_viewers', 'total_streaming_minutes', 'daily_streaming_minutes', 
                      'followers_count', 'tweets_count', 'total_xp', 'views']
    
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    
    # Data overview
    st.sidebar.header("📊 Data Overview")
    st.sidebar.metric("Total Streamers", len(df))
    
    if 'is_live' in df.columns:
        live_count = len(df[df['is_live'] == 'Yes'])
        st.sidebar.metric("Currently Live", live_count)
        st.sidebar.metric("Offline", len(df) - live_count)
    
    # Display database info
    if db_name and collection_name:
        st.sidebar.info(f"📊 **Database:** {db_name}\n📄 **Collection:** {collection_name}")
    
    # Filters section
    st.sidebar.header("🔍 Filters")
    
    # Initialize filters
    filters = {}
    
    # Search box
    filters['search_term'] = st.sidebar.text_input("🔍 Search (Username, Game, Language, Twitter)", "")
    
    # Status filter
    status_options = ["All"] + list(df['is_live'].unique()) if 'is_live' in df.columns else ["All"]
    filters['status_filter'] = st.sidebar.selectbox("📡 Live Status", status_options)
    
    # Verification filter
    verification_options = ["All"] + list(df['isVerified'].unique()) if 'isVerified' in df.columns else ["All"]
    filters['verification_filter'] = st.sidebar.selectbox("✅ Verification Status", verification_options)
    
    # Numeric filters with safe slider implementation
    if 'current_viewers' in df.columns:
        viewer_range = safe_slider("👥 Current Viewers Range", df['current_viewers'], "viewers")
        if viewer_range:
            filters['viewer_range'] = viewer_range
    
    if 'total_streaming_minutes' in df.columns:
        streaming_range = safe_slider("⏱️ Total Streaming Time (minutes)", df['total_streaming_minutes'], "streaming")
        if streaming_range:
            filters['streaming_time_range'] = streaming_range
    
    # Apply filters
    filtered_df = apply_filters(df, filters)
    
    # Main content area
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("📊 Filtered Results", len(filtered_df))
    
    with col2:
        if 'current_viewers' in filtered_df.columns:
            total_viewers = int(filtered_df['current_viewers'].sum())
            st.metric("👥 Total Current Viewers", f"{total_viewers:,}")
    
    with col3:
        if 'total_streaming_minutes' in filtered_df.columns:
            total_hours = filtered_df['total_streaming_minutes'].sum() / 60
            st.metric("⏰ Total Streaming Hours", f"{total_hours:,.1f}")
    
    with col4:
        if 'isVerified' in filtered_df.columns:
            verified_count = len(filtered_df[filtered_df['isVerified'] == 'Yes'])
            st.metric("✅ Verified Streamers", verified_count)
    
    # Sorting options
    st.header("📋 Data Table")
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        # Column selection for sorting
        numeric_columns = filtered_df.select_dtypes(include=['number']).columns.tolist()
        available_columns = ['username'] + numeric_columns
        sort_column = st.selectbox("Sort by", available_columns)
    
    with col2:
        sort_order = st.selectbox("Order", ["Ascending", "Descending"])
    
    with col3:
        # Records per page
        records_per_page = st.selectbox("Records per page", [25, 50, 100, 200], index=1)
    
    # Sort the dataframe
    if sort_column in filtered_df.columns:
        ascending = sort_order == "Ascending"
        filtered_df = filtered_df.sort_values(by=sort_column, ascending=ascending)
    
    # Pagination
    total_records = len(filtered_df)
    total_pages = (total_records - 1) // records_per_page + 1 if total_records > 0 else 1
    
    if total_pages > 1:
        page = st.number_input("Page", min_value=1, max_value=total_pages, value=1) - 1
        start_idx = page * records_per_page
        end_idx = min(start_idx + records_per_page, total_records)
        display_df = filtered_df.iloc[start_idx:end_idx]
        st.info(f"Showing records {start_idx + 1} to {end_idx} of {total_records}")
    else:
        display_df = filtered_df
    
    # Display table
    if not display_df.empty:
        # Format numeric columns
        formatted_df = display_df.copy()
        
        # Format specific columns for better display
        if 'total_streaming_minutes' in formatted_df.columns:
            formatted_df['total_streaming_hours'] = (formatted_df['total_streaming_minutes'] / 60).round(2)
        
        if 'daily_streaming_minutes' in formatted_df.columns:
            formatted_df['daily_streaming_hours'] = (formatted_df['daily_streaming_minutes'] / 60).round(2)
        
        # Reorder columns for better display
        priority_columns = ['username', 'is_live', 'current_viewers', 'game_name', 'language', 
                          'isVerified', 'total_streaming_hours', 'daily_streaming_hours', 
                          'followers_count', 'twitter_verified']
        
        displayed_columns = [col for col in priority_columns if col in formatted_df.columns]
        remaining_columns = [col for col in formatted_df.columns if col not in displayed_columns]
        final_columns = displayed_columns + remaining_columns
        
        st.dataframe(
            formatted_df[final_columns],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No data matches the current filters.")
    
    # Export options
    if not filtered_df.empty:
        st.header("📥 Export Data")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("📄 Export as CSV", type="secondary"):
                csv = filtered_df.to_csv(index=False)
                st.download_button(
                    label="⬇️ Download CSV",
                    data=csv,
                    file_name=f"streamers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("📊 Export as Excel", type="secondary"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, index=False, sheet_name='Streamers')
                    
                st.download_button(
                    label="⬇️ Download Excel",
                    data=output.getvalue(),
                    file_name=f"streamers_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with col3:
            if st.button("📋 Copy to Clipboard", type="secondary"):
                csv_data = filtered_df.to_csv(index=False)
                st.code(csv_data, language="csv")
                st.info("CSV data displayed above. Use Ctrl+A to select all, then Ctrl+C to copy.")
    
    # Charts section
    if len(filtered_df) > 0:
        st.header("📊 Analytics Charts")
        
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            if 'is_live' in filtered_df.columns:
                # Live status distribution
                live_counts = filtered_df['is_live'].value_counts()
                if not live_counts.empty:
                    fig_pie = px.pie(
                        values=live_counts.values, 
                        names=live_counts.index,
                        title="Live Status Distribution",
                        color_discrete_sequence=px.colors.qualitative.Set3
                    )
                    st.plotly_chart(fig_pie, use_container_width=True)
        
        with chart_col2:
            if 'current_viewers' in filtered_df.columns and filtered_df['current_viewers'].sum() > 0:
                # Top streamers by current viewers
                top_streamers = filtered_df.nlargest(10, 'current_viewers')
                if not top_streamers.empty:
                    fig_bar = px.bar(
                        top_streamers,
                        x='current_viewers',
                        y='username',
                        orientation='h',
                        title="Top 10 Streamers by Current Viewers",
                        color='current_viewers',
                        color_continuous_scale='viridis'
                    )
                    fig_bar.update_layout(height=400)
                    st.plotly_chart(fig_bar, use_container_width=True)
        
        # Additional charts
        if 'game_name' in filtered_df.columns:
            st.subheader("🎮 Popular Games")
            game_counts = filtered_df['game_name'].value_counts().head(10)
            if not game_counts.empty and len(game_counts) > 0:
                fig_games = px.bar(
                    x=game_counts.index,
                    y=game_counts.values,
                    title="Top 10 Most Streamed Games",
                    labels={'x': 'Game', 'y': 'Number of Streamers'}
                )
                fig_games.update_layout(xaxis_tickangle=45)
                st.plotly_chart(fig_games, use_container_width=True)
    
    # Footer
    st.markdown("---")
    st.markdown(
        f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"**Total records:** {len(filtered_df):,} | "
        f"**MongoDB:** {db_name}.{collection_name}"
    )

if __name__ == "__main__":
    main()