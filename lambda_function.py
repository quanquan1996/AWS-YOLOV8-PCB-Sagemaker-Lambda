import json
import base64
import tempfile
import os
import cv2
import numpy as np
from ultralytics import YOLO
import boto3
from PIL import Image
import io

# 模型路径 - 现在直接从Docker镜像中读取
MODEL_LOCAL_PATH = os.path.join(os.environ['LAMBDA_TASK_ROOT'], 'models/best.pt')

# 缺陷名称映射
defect_names_map = {
    0: "Missing hole",
    1: "Mouse bite",
    2: "Open circuit",
    3: "Short",
    4: "Spur",
    5: "Supurious copper"
}

def process_image(image_data):
    """处理图像并进行缺陷检测"""
    # 从base64解码图像
    image_bytes = base64.b64decode(image_data)

    # 转换为PIL图像
    img = Image.open(io.BytesIO(image_bytes))

    # 加载模型
    model = YOLO(MODEL_LOCAL_PATH)

    # 预测
    results = model.predict(img)

    # 处理结果
    boxes = results[0].boxes

    # 将图像转换为OpenCV格式以便绘制
    plotted_img = results[0].plot()

    # 将绘制后的图像编码为base64
    _, buffer = cv2.imencode('.jpg', plotted_img)
    plotted_base64 = base64.b64encode(buffer).decode('utf-8')

    # 提取缺陷信息
    defects = []
    if len(boxes) > 0:
        defect_indices = boxes.cls.cpu().numpy()
        confidences = boxes.conf.cpu().numpy()

        for i, cls_idx in enumerate(defect_indices):
            cls_idx = int(cls_idx)
            if cls_idx in defect_names_map:
                defects.append({
                    "type": defect_names_map[cls_idx],
                    "confidence": float(confidences[i])
                })

    # 计算缺陷摘要
    defect_summary = {}
    for defect in defects:
        defect_type = defect["type"]
        if defect_type in defect_summary:
            defect_summary[defect_type] += 1
        else:
            defect_summary[defect_type] = 1

    return {
        "processed_image": plotted_base64,
        "defects": defects,
        "defect_count": len(defects),
        "defect_summary": defect_summary
    }

def process_video(video_data):
    """处理视频并进行缺陷检测"""
    # 从base64解码视频
    video_bytes = base64.b64decode(video_data)

    # 保存到临时文件
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
    temp_file.write(video_bytes)
    temp_file.close()

    # 加载模型
    model = YOLO(MODEL_LOCAL_PATH)

    # 打开视频
    cap = cv2.VideoCapture(temp_file.name)
    if not cap.isOpened():
        raise Exception("Error opening video file")

    # 视频信息
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 处理结果
    all_defects = []
    frame_results = []
    sample_frames = []  # 存储几个关键帧

    # 每隔几帧处理一次，以提高效率
    frame_interval = max(1, int(frame_count / 20))  # 最多处理20帧

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            # 预测当前帧
            results = model.predict(frame, conf=0.75)

            # 处理结果
            boxes = results[0].boxes
            plotted_frame = results[0].plot()

            # 将关键帧编码为base64
            _, buffer = cv2.imencode('.jpg', plotted_frame)
            frame_base64 = base64.b64encode(buffer).decode('utf-8')

            # 添加到样本帧
            if len(sample_frames) < 5:  # 最多保存5个样本帧
                sample_frames.append(frame_base64)

            # 提取缺陷信息
            frame_defects = []
            if len(boxes) > 0:
                defect_indices = boxes.cls.cpu().numpy()
                confidences = boxes.conf.cpu().numpy()

                for i, cls_idx in enumerate(defect_indices):
                    cls_idx = int(cls_idx)
                    if cls_idx in defect_names_map:
                        defect = {
                            "type": defect_names_map[cls_idx],
                            "confidence": float(confidences[i]),
                            "frame": frame_idx
                        }
                        frame_defects.append(defect)
                        all_defects.append(defect)

            frame_results.append({
                "frame_index": frame_idx,
                "defects": frame_defects
            })

        frame_idx += 1

    # 释放资源
    cap.release()
    os.unlink(temp_file.name)

    # 计算缺陷摘要
    defect_summary = {}
    for defect in all_defects:
        defect_type = defect["type"]
        if defect_type in defect_summary:
            defect_summary[defect_type] += 1
        else:
            defect_summary[defect_type] = 1

    return {
        "sample_frames": sample_frames,
        "defects": all_defects,
        "defect_count": len(all_defects),
        "defect_summary": defect_summary,
        "total_frames": frame_count,
        "fps": fps
    }

def lambda_handler(event, context):
    """Lambda处理函数"""
    try:
        # 打印模型路径以便调试
        print(f"Using model at: {MODEL_LOCAL_PATH}")
        print(f"Model exists: {os.path.exists(MODEL_LOCAL_PATH)}")

        # 解析请求体
        file_type = event.get('file_type')
        file_data = event.get('file_data')

        if not file_data:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'No file data provided'})
            }

        # 处理图像或视频
        if file_type == 'image':
            result = process_image(file_data)
        elif file_type == 'video':
            result = process_video(file_data)
        else:
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'error': 'Unsupported file type'})
            }

        # 返回结果
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result)
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()

        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'error': str(e)})
        }
