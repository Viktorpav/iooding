from django import forms
from ckeditor5.widgets import CKEditor5Widget
from .models import Post  # replace with your model

class PostForm(forms.ModelForm):
    content = forms.CharField(widget=CKEditor5Widget(config_name='default'))

    class Meta:
        model = Post
        fields = '__all__'
