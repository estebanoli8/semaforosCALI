import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from ..contracts import boxes
from ..files import sha256
def open_image(path):
    with Image.open(path) as raw:
        return ImageOps.exif_transpose(raw).convert('RGB')


def detect(path, config, output_dir):
    import torch
    from ultralytics import YOLO
    weights=Path(config['weights'])
    if not weights.is_file():raise ValueError('detector_weights_not_installed')
    digest=sha256(weights)
    if config.get('expected_sha256') and digest!=config['expected_sha256']:raise ValueError('detector_digest_mismatch')
    torch.set_num_threads(config['cpu_threads'])
    model=YOLO(str(weights))
    ids=[int(k) for k,v in model.names.items() if v=='traffic light']
    if not ids:raise ValueError('detector_has_no_traffic_light_class')
    image=open_image(path);width,height=image.size
    result=model.predict(source=image,device='cpu',classes=ids,imgsz=config['image_size'],conf=config['confidence'],iou=config['iou'],max_det=config['max_detections'],verbose=False)[0]
    objects=[]
    for box in result.boxes:
        x1,y1,x2,y2=box.xyxy[0].tolist()
        coords=[max(0,math.floor(x1)),max(0,math.floor(y1)),min(width,math.ceil(x2)),min(height,math.ceil(y2))]
        if coords[0]>=coords[2] or coords[1]>=coords[3]:continue
        objects.append({'bbox':coords,'score':float(box.conf[0])})
    objects=boxes(objects,width,height)
    drawing=ImageDraw.Draw(image)
    for n,item in enumerate(objects):
        drawing.rectangle(item['bbox'],outline='red',width=3)
        drawing.text((item['bbox'][0],item['bbox'][1]),str(n+1),fill='red')
    annotation=Path(output_dir)/'anotada.jpg';image.save(annotation,quality=92)
    return {'objects':objects,'width':width,'height':height,'orientation':'exif_transposed','annotation':str(annotation)}, {'provider':'ultralytics_local','weights':weights.name,'sha256':digest}
