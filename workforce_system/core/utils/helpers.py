from django.utils import timezone
from django.db import IntegrityError, transaction

import cv2, dlib, os

from core.models import Holiday
from core.data.holidays import HOLIDAYS

BASE_DIR = os.path.dirname(__file__)
OFFSET = 0.2

model_path = os.path.join(BASE_DIR, "..", "models", "shape_predictor_68_face_landmarks.dat")
model_path = os.path.abspath(model_path)

detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(model_path)

history = []

def get_head_turn_direction(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = detector(gray)

    if len(faces) == 0:
        return (None, None)

    face = faces[0]
    landmarks = predictor(gray, face)

    left_eye_x = (landmarks.part(36).x + landmarks.part(39).x) / 2
    right_eye_x = (landmarks.part(42).x + landmarks.part(45).x) / 2
    nose_x = landmarks.part(30).x

    mid_eye_x = (left_eye_x + right_eye_x) / 2
    face_width = right_eye_x - left_eye_x
    if face_width == 0:
        return (None, None)
    offset = (nose_x - mid_eye_x) / face_width

    current_direction = ''
    if offset < -OFFSET:
        current_direction = 'RIGHT'
    elif offset > OFFSET:
        current_direction = 'LEFT'
    else:
        current_direction = 'CENTER'

    history.append(current_direction)
    if len(history) > 5: history.pop(0)

    if history.count('LEFT') >= 4:
        history.clear()
        return ('LEFT', 'CENTER')
    elif history.count('RIGHT') >= 4:
        history.clear()
        return ('RIGHT', 'CENTER')
    else:
        last = history[-1] if history else 'CENTER'
        return ('CENTER', last)
    
#-------- HOLIDAYS --------

@transaction.atomic
def populate_holidays(year):

    holidays = HOLIDAYS.get(year, [])

    for h in holidays:
        try:
            Holiday.objects.create(
                date=h["date"],
                name=h["name"]
            )
        except IntegrityError:
            continue

def ensure_holidays_exist():
    today = timezone.now().date()
    year = today.year

    exists = Holiday.objects.filter(date__year=year).exists()

    if not exists:
        populate_holidays(year)