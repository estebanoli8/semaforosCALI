"""Métricas contra etiquetas humanas; nunca sustituyen ni alteran la predicción."""
import re


def wer(reference, hypothesis):
    if not isinstance(reference,str) or not isinstance(hypothesis,str):raise ValueError('text_label_required')
    ref=re.findall(r'\w+',reference.casefold());hyp=re.findall(r'\w+',hypothesis.casefold())
    previous=list(range(len(hyp)+1))
    for i,a in enumerate(ref,1):
        current=[i]
        for j,b in enumerate(hyp,1):
            current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(a!=b)))
        previous=current
    return {'wer':previous[-1]/len(ref) if ref else None,'word_errors':previous[-1],'reference_words':len(ref),
            'normalization':'casefold_unicode_words_without_punctuation'}


def iou(a,b):
    for box in (a,b):
        if len(box)!=4 or any(type(v) not in (int,float) for v in box) or box[2]<=box[0] or box[3]<=box[1]:raise ValueError('invalid_label_box')
    intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
    union=(a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection
    return intersection/union


def detection_metrics(predicted, labels, threshold=0.5):
    used=set();matches=0
    for p in sorted(predicted,key=lambda x:x['score'],reverse=True):
        candidates=[(iou(p['bbox'],b),i) for i,b in enumerate(labels) if i not in used]
        if candidates:
            overlap,index=max(candidates)
            if overlap>=threshold:used.add(index);matches+=1
    return {'precision':matches/len(predicted) if predicted else None,'recall':matches/len(labels) if labels else None,
            'true_positive':matches,'false_positive':len(predicted)-matches,'false_negative':len(labels)-matches,'iou_threshold':threshold}


def light_metrics(predicted, labels):
    correct=0;answered=0;known=0
    for key in ('red','yellow','green'):
        truth=labels.get(key);guess=predicted.get(key)
        if truth is not None and type(truth) is not bool:raise ValueError('invalid_light_label')
        if truth is None:continue
        known+=1
        if guess is not None:answered+=1;correct+=int(guess==truth)
    return {'accuracy_answered':correct/answered if answered else None,'coverage':answered/known if known else None,
            'known_lights':known,'answered_lights':answered,'correct_lights':correct}
