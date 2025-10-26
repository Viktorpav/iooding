from django import forms
from .models import Post


class CommentForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ('name', 'email', 'body')
        widgets = {
            'body': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Enter your comment...'
            }),
        }