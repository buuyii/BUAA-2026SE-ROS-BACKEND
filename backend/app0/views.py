from django.shortcuts import render
from django.shortcuts import HttpResponse

# Create your views here.
def test(request):
    return HttpResponse("Hello, this is robot-backend")