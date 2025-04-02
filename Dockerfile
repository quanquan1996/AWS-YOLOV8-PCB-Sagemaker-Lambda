FROM public.ecr.aws/lambda/python:3.12

# 安装系统依赖（OpenCV可能需要的一些系统库）
RUN dnf update -y && \
    dnf install -y mesa-libGL mesa-libGLU libglvnd-glx && \
    dnf clean all

# 复制requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# 安装Python依赖
RUN pip install -r requirements.txt --no-cache-dir

# 创建模型目录并复制模型文件
RUN mkdir -p ${LAMBDA_TASK_ROOT}/models
COPY models/best.pt ${LAMBDA_TASK_ROOT}/models/

# 复制Lambda函数代码
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

# 设置Lambda处理程序
CMD [ "lambda_function.lambda_handler" ]
