FROM nvcr.io/nvidia/deepstream:6.0-triton

RUN apt-key del 7fa2af80 && \
    apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/3bf863cc.pub

RUN apt update && \
    apt install -y python3-gi \
    python3-dev python3-gst-1.0 \
    python-gi-dev python-dev python3.8-dev \
    git cmake g++ build-essential \
    libglib2.0-dev libglib2.0-dev-bin \
    libtool m4 autoconf automake 

RUN apt install -y python-is-python3 \
    && apt-get clean -y && apt-get autoclean -y && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Build gst-python and pyds
RUN git clone -b v1.1.1 https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/ pyapps && \
    cd pyapps && pip3 install -U pip && \
    git config --global http.sslverify false && \
    git submodule update --init && \
    cd 3rdparty/gst-python && ./autogen.sh && \
    make -j8 && make install && \
    cd ../pybind11/ && python3 setup.py install && \
    cd ../../bindings && mkdir build && cd build && \
    cmake ..  -DPYTHON_MAJOR_VERSION=3 -DPYTHON_MINOR_VERSION=8 -DS_PATH=/opt/nvidia/deepstream/deepstream-6.0/ && \
    make -j8 && pip3 install pyds-1.1.1-py3-none-linux_x86_64.whl

COPY ./requirements.txt ./app/requirements.txt

RUN pip3 install -r ./app/requirements.txt

COPY . ./app
WORKDIR /opt/nvidia/deepstream/deepstream-6.0/app

RUN ln -s /usr/lib/x86_64-linux-gnu/libpython3.8.so /usr/lib/libpython3.8.so

ENV GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0:/opt/nvidia/deepstream/deepstream-6.0/app/plugins

CMD python3 pipeline.py configs/main_config.yml
ENV GST_DEBUG=2