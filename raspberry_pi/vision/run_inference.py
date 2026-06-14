import numpy as np, tensorflow as tf
from PIL import Image
model_path='/home/jaggu524/farm-robo/raspberry_pi/vision/models/plant_disease.tflite'
labels_path='/home/jaggu524/farm-robo/raspberry_pi/vision/models/labels.txt'
img_path='/home/jaggu524/farm-robo/raspberry_pi/vision/models/sample_leaf.jpg'

img=Image.open(img_path).convert('RGB').resize((200,200))
x=np.expand_dims(np.array(img,dtype=np.float32)/255.0,0)
interpreter=tf.lite.Interpreter(model_path=model_path)
interpreter.allocate_tensors()
input_index=interpreter.get_input_details()[0]['index']
output_index=interpreter.get_output_details()[0]['index']
interpreter.set_tensor(input_index,x)
interpreter.invoke()
pred=interpreter.get_tensor(output_index)[0]
labels=[l.strip() for l in open(labels_path).read().splitlines()]
if len(labels)<len(pred):
    labels += ["Class_{}".format(i) for i in range(len(labels), len(pred))]

top3=pred.argsort()[-3:][::-1]
for i in top3:
    print("{}: {:.4f}".format(labels[i], float(pred[i])))
