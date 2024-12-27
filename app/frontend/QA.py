import streamlit as st
from utils import sync_upload_to_minio, sync_process_document, send_message



# Configure Streamlit page layout
st.set_page_config(layout="wide")

# Initialize session state for chat history and references
if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []  # Stores chat conversation history
if "references" not in st.session_state:
    st.session_state["references"] = []  # Stores reference documents or URLs
if "messages" not in st.session_state:
    st.session_state["messages"] = []  # Chat messages history
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0
if "contexts" not in st.session_state:
    st.session_state.contexts = []


def update_key():
    st.session_state.uploader_key += 1

# Streamlit app setup
st.title("Multi-Document Chatbot")
st.sidebar.title("Manage Reference Documents")

# Sidebar for document upload options
upload_option = st.sidebar.radio("Add Reference Source", ("Website URL", "Upload Files"))



# Handle document input
if upload_option == "Website URL":
    url = st.sidebar.text_input("Enter Website URL:")
    if st.sidebar.button("Add URL"):
        if url:
            st.session_state["references"].append(f"URL: {url}")
            st.sidebar.success(f"Added URL: {url}")

            # TODO
            sync_upload_to_minio("my-bucket", "user123", "chat456", "Website URL", url=url)
            sync_process_document("user123", "chat456", "Website URL", url=url)



elif upload_option == "Upload Files":
    uploaded_files = st.sidebar.file_uploader("Upload your files (txt/pdf):", type=["txt", "pdf"], accept_multiple_files=True)
    if st.sidebar.button("Add Files"):
        if uploaded_files:

            # TODO
            sync_upload_to_minio("my-bucket", "user123", "chat456", "Upload Files", uploaded_files=uploaded_files)
            sync_process_document("user123", "chat456", "Upload Files", uploaded_files=uploaded_files)

            for uploaded_file in uploaded_files:
                st.session_state["references"].append(f"File: {uploaded_file.name}")
            st.sidebar.success(f"Added {len(uploaded_files)} files.")
            # st.rerun() 

# Display current reference sources
st.sidebar.subheader("Current References")
if st.session_state["references"]:
    for i, ref in enumerate(st.session_state["references"]):
        col1, col2 = st.sidebar.columns([4, 1])
        with col1:
            st.write(ref)
        with col2:
            if st.button("Remove", key=f"remove_{i}"):
                st.session_state["references"].pop(i)
                st.sidebar.success(f"Removed: {ref}")
                st.rerun()  # Refresh the sidebar to reflect the changes
else:
    st.sidebar.info("No reference documents added yet.")

# Display chat interface and history
# st.header("Chat Interface")
for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input and chatbot response
if prompt := st.chat_input("Ask your question:"):
    if prompt == "/clear":
        # Clear chat history
        st.session_state["messages"].clear()
        st.info("Chat history cleared.")
    else:
        # Display user message
        with st.chat_message("user"):
            st.markdown(prompt)
        # Add user message to chat history
        st.session_state["messages"].append({"role": "user", "content": prompt})

        # Generate a simulated response
        with st.chat_message("assistant"):
            st.write_stream(
                send_message(user_id="user123", chat_id="chat456", message=prompt)
            )

            # Add assistant response to chat history
        #     st.session_state.messages.append(
        #         {
        #             "role": "assistant",
        #             "content": response,
        #         }
        #     )

        # # Add assistant response to chat history
        # st.session_state["messages"].append({"role": "assistant", "content": response})